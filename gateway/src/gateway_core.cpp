#include "gateway_core.hpp"

#include <cmath>
#include <stdexcept>

namespace r1::motion {
namespace {
constexpr double kMaxVx = 0.15;
constexpr double kMaxVy = 0.10;
constexpr double kMaxMoveDuration = 2.0;
constexpr double kMaxTurnDegrees = 30.0;
constexpr double kMaxTurnRate = 0.2;
}  // namespace

GatewayCore::GatewayCore(RobotHardware& hardware) : hardware_(hardware) {}

GatewayCore::~GatewayCore() {
  cancelled_ = true;
  hardware_.StopAndRelease();
  if (worker_.joinable()) worker_.join();
}

void GatewayCore::InstallAction(std::string action) {
  std::lock_guard<std::mutex> lock(mutex_);
  installed_actions_.insert(std::move(action));
}

ValidationResult GatewayCore::Validate(const MotionPlan& plan) const {
  ValidationResult result;
  if (plan.schema_version != "motion-plan/v2")
    result.errors.emplace_back("unsupported schema version");
  if (plan.plan_id.empty()) result.errors.emplace_back("plan_id is required");
  if (!plan.require_operator_enable)
    result.errors.emplace_back("operator enable must be required");
  if (plan.steps.empty() || plan.steps.size() > 16)
    result.errors.emplace_back("plan must contain 1 to 16 steps");
  std::lock_guard<std::mutex> lock(mutex_);
  for (const auto& step : plan.steps) {
    if (const auto* action = std::get_if<ActionStep>(&step)) {
      if (!installed_actions_.count(action->action))
        result.errors.emplace_back("action is not installed: " + action->action);
    } else if (const auto* move = std::get_if<MoveForStep>(&step)) {
      if (std::abs(move->vx_mps) > kMaxVx || std::abs(move->vy_mps) > kMaxVy ||
          move->duration_s <= 0 || move->duration_s > kMaxMoveDuration)
        result.errors.emplace_back("move_for exceeds bounded locomotion limits");
    } else if (const auto* turn = std::get_if<TurnRelativeStep>(&step)) {
      if (std::abs(turn->angle_deg) > kMaxTurnDegrees)
        result.errors.emplace_back("turn_relative exceeds 30 degrees");
    } else if (const auto* wait = std::get_if<WaitStep>(&step)) {
      if (wait->duration_s < 0.1 || wait->duration_s > 10)
        result.errors.emplace_back("wait duration is out of range");
    } else if (const auto* say = std::get_if<SayStep>(&step)) {
      if (say->text.empty() || say->text.size() > 600)
        result.errors.emplace_back("say text is out of range");
    }
  }
  result.valid = result.errors.empty();
  return result;
}

std::string GatewayCore::Execute(const MotionPlan& plan,
                                 const std::string& idempotency_key,
                                 bool operator_enabled, EventSink events) {
  const auto validation = Validate(plan);
  if (!validation.valid) throw std::invalid_argument(validation.errors.front());
  if (!operator_enabled) throw std::invalid_argument("operator enable is required");
  const auto status = hardware_.ReadStatus();
  if (!status.connected || !status.lowstate_fresh || status.fsm_id != 811)
    throw std::runtime_error("robot is not ready in FSM 811 with fresh LowState");
  std::lock_guard<std::mutex> lock(mutex_);
  if (idempotency_key.empty()) throw std::invalid_argument("idempotency key is required");
  if (idempotency_key == last_idempotency_key_) return last_execution_id_;
  if (!active_execution_id_.empty()) throw std::runtime_error("another plan is executing");
  if (worker_.joinable()) worker_.join();
  active_execution_id_ = "exec-" + plan.plan_id;
  last_idempotency_key_ = idempotency_key;
  last_execution_id_ = active_execution_id_;
  cancelled_ = false;
  worker_ = std::thread(&GatewayCore::Run, this, active_execution_id_, plan, events);
  return active_execution_id_;
}

bool GatewayCore::Cancel(const std::string& execution_id) {
  std::lock_guard<std::mutex> lock(mutex_);
  if (execution_id != active_execution_id_ || execution_id.empty()) return false;
  cancelled_ = true;
  hardware_.StopAndRelease();
  return true;
}

RobotStatus GatewayCore::Status() {
  auto status = hardware_.ReadStatus();
  std::lock_guard<std::mutex> lock(mutex_);
  status.executing = !active_execution_id_.empty();
  status.execution_id = active_execution_id_;
  return status;
}

void GatewayCore::Run(std::string execution_id, MotionPlan plan, EventSink events) {
  events("started", -1, execution_id);
  bool passed = true;
  for (std::size_t index = 0; index < plan.steps.size() && !cancelled_; ++index) {
    events("step_started", static_cast<int>(index), "");
    const auto& step = plan.steps[index];
    bool step_passed = true;
    if (const auto* action = std::get_if<ActionStep>(&step)) {
      step_passed = hardware_.ExecuteInstalledAction(action->action, cancelled_);
    } else if (const auto* move = std::get_if<MoveForStep>(&step)) {
      step_passed = hardware_.MoveFor(move->vx_mps, move->vy_mps,
                                      move->duration_s, cancelled_);
      hardware_.StopAndRelease();
    } else if (const auto* turn = std::get_if<TurnRelativeStep>(&step)) {
      step_passed = hardware_.TurnRelative(turn->angle_deg, kMaxTurnRate, cancelled_);
      hardware_.StopAndRelease();
    } else if (const auto* wait = std::get_if<WaitStep>(&step)) {
      const auto end = std::chrono::steady_clock::now() +
                       std::chrono::duration<double>(wait->duration_s);
      while (!cancelled_ && std::chrono::steady_clock::now() < end)
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    if (!step_passed) {
      passed = false;
      events("step_failed", static_cast<int>(index), "hardware adapter rejected step");
      break;
    }
    events("step_completed", static_cast<int>(index), "");
  }
  hardware_.StopAndRelease();
  events(cancelled_ ? "cancelled" : passed ? "completed" : "failed", -1, "");
  std::lock_guard<std::mutex> lock(mutex_);
  if (active_execution_id_ == execution_id) active_execution_id_.clear();
}

}  // namespace r1::motion
