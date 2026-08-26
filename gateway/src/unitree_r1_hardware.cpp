#include "unitree_r1_hardware.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <thread>
#include <iostream>

#include <unitree/robot/channel/channel_factory.hpp>

namespace r1::motion {
namespace {
constexpr int kReadyFsm = 811;
constexpr double kPi = 3.14159265358979323846;
double Wrap(double value) {
  while (value > kPi) value -= 2.0 * kPi;
  while (value < -kPi) value += 2.0 * kPi;
  return value;
}
}  // namespace

UnitreeR1Hardware::UnitreeR1Hardware(std::string network_interface)
    : network_interface_(std::move(network_interface)) {
  unitree::robot::ChannelFactory::Instance()->Init(0, network_interface_);
  last_lowstate_ = std::chrono::steady_clock::now() - std::chrono::seconds(2);
  lowstate_ = std::make_shared<unitree::robot::ChannelSubscriber<unitree_hg::msg::dds_::LowState_>>("rt/lowstate");
  lowstate_->InitChannel([this](const void* message) {
    std::lock_guard<std::mutex> lock(lowstate_mutex_);
    lowstate_message_ = *static_cast<const unitree_hg::msg::dds_::LowState_*>(message);
    last_lowstate_ = std::chrono::steady_clock::now();
  }, 1);
  loco_ = std::make_unique<unitree::robot::r1::LocoClient>();
  loco_->Init();
  loco_->SetTimeout(2.f);
}

RobotStatus UnitreeR1Hardware::ReadStatus() {
  RobotStatus status;
  int fsm_id = -1;
  int fsm_mode = -1;
  const int fsm_result = loco_->GetFsmId(fsm_id);
  const int mode_result = loco_->GetFsmMode(fsm_mode);
  // R1 firmware reliably exposes FSM ID, while some versions return an
  // error for the optional FSM mode query. Keep that diagnostic without
  // treating the robot as disconnected when the safety-critical ID and
  // LowState checks are healthy.
  status.connected = fsm_result == 0;
  status.fsm_id = fsm_id;
  status.fsm_mode = fsm_mode;
  {
    std::lock_guard<std::mutex> lock(lowstate_mutex_);
    status.lowstate_fresh = std::chrono::steady_clock::now() - last_lowstate_ <= std::chrono::seconds(1);
  }
  if (!status.connected) status.fault = "LocoClient FSM ID query failed";
  else if (mode_result != 0) status.fault = "FSM mode query unavailable on this firmware";
  if (!status.lowstate_fresh) status.fault = "rt/lowstate is stale";
  return status;
}

bool UnitreeR1Hardware::Ready(RobotStatus* output) {
  const auto status = ReadStatus();
  if (output) *output = status;
  return status.connected && status.lowstate_fresh && status.fsm_id == kReadyFsm;
}

bool UnitreeR1Hardware::ExecuteInstalledAction(const std::string&, std::atomic_bool&) {
  return false;
}

bool UnitreeR1Hardware::MoveFor(double vx, double vy, double duration,
                                std::atomic_bool& cancelled) {
  if (!Ready()) return false;
  const int move_result = loco_->SetVelocity(static_cast<float>(vx), static_cast<float>(vy), 0.0f,
                                              static_cast<float>(duration));
  std::cerr << "R1 LocoClient::SetVelocity vx=" << vx << " vy=" << vy
            << " duration=" << duration
            << " result=" << move_result << '\n';
  if (move_result != 0) {
    StopAndRelease();
    return false;
  }
  const auto deadline = std::chrono::steady_clock::now() +
                        std::chrono::duration<double>(duration);
  while (std::chrono::steady_clock::now() < deadline) {
    if (cancelled.load() || !Ready()) {
      StopAndRelease();
      return false;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
  }
  const int stop_result = loco_->StopMove();
  std::cerr << "R1 LocoClient::StopMove result=" << stop_result << '\n';
  return stop_result == 0;
}

double UnitreeR1Hardware::Yaw() const {
  std::lock_guard<std::mutex> lock(lowstate_mutex_);
  return static_cast<double>(lowstate_message_.imu_state().rpy()[2]);
}

bool UnitreeR1Hardware::TurnRelative(double angle_deg, double maximum_rate_rad_s,
                                     std::atomic_bool& cancelled) {
  if (!Ready()) return false;
  const double target = Wrap(Yaw() + angle_deg * kPi / 180.0);
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(20);
  while (std::chrono::steady_clock::now() < deadline) {
    if (cancelled.load() || !Ready()) {
      StopAndRelease();
      return false;
    }
    const double error = Wrap(target - Yaw());
    if (std::abs(error) <= 1.5 * kPi / 180.0) {
      const int stop_result = loco_->StopMove();
      std::cerr << "R1 LocoClient::StopMove result=" << stop_result << '\n';
      return stop_result == 0;
    }
    const double rate = std::clamp(error * 1.5, -maximum_rate_rad_s, maximum_rate_rad_s);
    if (loco_->Move(0.0f, 0.0f, static_cast<float>(rate)) != 0) {
      StopAndRelease();
      return false;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
  }
  StopAndRelease();
  return false;
}

void UnitreeR1Hardware::StopAndRelease() noexcept {
  try {
    if (loco_) std::cerr << "R1 LocoClient::StopMove result=" << loco_->StopMove() << '\n';
  } catch (...) {}
}

}  // namespace r1::motion
