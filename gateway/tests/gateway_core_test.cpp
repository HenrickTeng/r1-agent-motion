#include "gateway_core.hpp"

#include <gtest/gtest.h>

namespace {
class FakeHardware final : public r1::motion::RobotHardware {
 public:
  r1::motion::RobotStatus ReadStatus() override {
    r1::motion::RobotStatus status;
    status.connected = true;
    status.fsm_id = 811;
    status.fsm_mode = 0;
    status.lowstate_fresh = true;
    return status;
  }
  bool ExecuteInstalledAction(const std::string&, std::atomic_bool&) override { return true; }
  bool MoveFor(double, double, double, std::atomic_bool&) override { return true; }
  bool TurnRelative(double, double, std::atomic_bool&) override { return true; }
  void StopAndRelease() noexcept override { ++stop_count; }
  int stop_count{0};
};
}  // namespace

TEST(GatewayCore, RejectsUnknownActions) {
  FakeHardware hardware;
  r1::motion::GatewayCore gateway(hardware);
  r1::motion::MotionPlan plan{"motion-plan/v2", "test-001", {r1::motion::ActionStep{"dance"}}, true};
  const auto result = gateway.Validate(plan);
  EXPECT_FALSE(result.valid);
}

TEST(GatewayCore, RejectsUnsafeMovement) {
  FakeHardware hardware;
  r1::motion::GatewayCore gateway(hardware);
  r1::motion::MotionPlan plan{"motion-plan/v2", "test-002", {r1::motion::MoveForStep{0.51, 0, 1}}, true};
  EXPECT_FALSE(gateway.Validate(plan).valid);
}

TEST(GatewayCore, RejectsUnverifiedFastBackwardMovement) {
  FakeHardware hardware;
  r1::motion::GatewayCore gateway(hardware);
  r1::motion::MotionPlan plan{"motion-plan/v2", "test-004", {r1::motion::MoveForStep{-0.51, 0, 1}}, true};
  EXPECT_FALSE(gateway.Validate(plan).valid);
}

TEST(GatewayCore, AcceptsInstalledBoundedPlan) {
  FakeHardware hardware;
  r1::motion::GatewayCore gateway(hardware);
  gateway.InstallAction("wrist_wave");
  r1::motion::MotionPlan plan{
      "motion-plan/v2", "test-003",
      {r1::motion::ActionStep{"wrist_wave"}, r1::motion::MoveForStep{0.1, 0, 1}}, true};
  EXPECT_TRUE(gateway.Validate(plan).valid);
}
