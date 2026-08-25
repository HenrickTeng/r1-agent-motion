#pragma once

#include <atomic>
#include <chrono>
#include <functional>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include <variant>
#include <vector>

namespace r1::motion {

struct SayStep { std::string text; };
struct ActionStep { std::string action; };
struct MoveForStep { double vx_mps; double vy_mps; double duration_s; };
struct TurnRelativeStep { double angle_deg; };
struct WaitStep { double duration_s; };
using PlanStep = std::variant<SayStep, ActionStep, MoveForStep, TurnRelativeStep, WaitStep>;

struct MotionPlan {
  std::string schema_version;
  std::string plan_id;
  std::vector<PlanStep> steps;
  bool require_operator_enable{true};
};

struct RobotStatus {
  bool connected{false};
  int fsm_id{-1};
  int fsm_mode{-1};
  bool lowstate_fresh{false};
  bool executing{false};
  std::string execution_id;
  std::string fault;
};

struct ValidationResult {
  bool valid{false};
  std::vector<std::string> errors;
};

class RobotHardware {
 public:
  virtual ~RobotHardware() = default;
  virtual RobotStatus ReadStatus() = 0;
  virtual bool ExecuteInstalledAction(const std::string& action,
                                      std::atomic_bool& cancelled) = 0;
  virtual bool MoveFor(double vx_mps, double vy_mps, double duration_s,
                       std::atomic_bool& cancelled) = 0;
  virtual bool TurnRelative(double angle_deg, double maximum_rate_rad_s,
                            std::atomic_bool& cancelled) = 0;
  virtual void StopAndRelease() noexcept = 0;
};

class GatewayCore {
 public:
  using EventSink = std::function<void(const std::string&, int, const std::string&)>;

  explicit GatewayCore(RobotHardware& hardware);
  ~GatewayCore();
  GatewayCore(const GatewayCore&) = delete;
  GatewayCore& operator=(const GatewayCore&) = delete;

  void InstallAction(std::string action);
  ValidationResult Validate(const MotionPlan& plan) const;
  std::string Execute(const MotionPlan& plan, const std::string& idempotency_key,
                      bool operator_enabled, EventSink events);
  bool Cancel(const std::string& execution_id);
  RobotStatus Status();

 private:
  void Run(std::string execution_id, MotionPlan plan, EventSink events);

  RobotHardware& hardware_;
  std::set<std::string> installed_actions_;
  std::atomic_bool cancelled_{false};
  mutable std::mutex mutex_;
  std::thread worker_;
  std::string active_execution_id_;
  std::string last_idempotency_key_;
  std::string last_execution_id_;
};

}  // namespace r1::motion
