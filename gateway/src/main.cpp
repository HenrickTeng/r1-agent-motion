#include "gateway_core.hpp"

#include <iostream>

namespace {
class RefusingHardware final : public r1::motion::RobotHardware {
 public:
  r1::motion::RobotStatus ReadStatus() override {
    r1::motion::RobotStatus status;
    status.fault = "Unitree hardware adapter is not linked";
    return status;
  }
  bool ExecuteInstalledAction(const std::string&, std::atomic_bool&) override { return false; }
  bool MoveFor(double, double, double, std::atomic_bool&) override { return false; }
  bool TurnRelative(double, double, std::atomic_bool&) override { return false; }
  void StopAndRelease() noexcept override {}
};
}  // namespace

int main() {
  RefusingHardware hardware;
  r1::motion::GatewayCore gateway(hardware);
  std::cout << "r1-gateway core built without the Unitree deployment adapter; refusing motion\n";
  return 0;
}
