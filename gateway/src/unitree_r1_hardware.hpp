#pragma once

#include "gateway_core.hpp"

#include <memory>
#include <string>

#include <unitree/idl/hg/LowState_.hpp>
#include <unitree/robot/channel/channel_subscriber.hpp>
#include <unitree/robot/r1/loco/r1_loco_client.hpp>

namespace r1::motion {

class UnitreeR1Hardware final : public RobotHardware {
 public:
  explicit UnitreeR1Hardware(std::string network_interface);
  ~UnitreeR1Hardware() override = default;

  RobotStatus ReadStatus() override;
  bool ExecuteInstalledAction(const std::string&, std::atomic_bool&) override;
  bool MoveFor(double, double, double, std::atomic_bool&) override;
  bool TurnRelative(double, double, std::atomic_bool&) override;
  bool TurnFor(double omega_rad_s, double duration, std::atomic_bool& cancelled);
  void StopAndRelease() noexcept override;

 private:
  double Yaw() const;
  bool Ready(RobotStatus* status = nullptr);

  std::unique_ptr<unitree::robot::r1::LocoClient> loco_;
  std::shared_ptr<unitree::robot::ChannelSubscriber<unitree_hg::msg::dds_::LowState_>> lowstate_;
  unitree_hg::msg::dds_::LowState_ lowstate_message_;
  mutable std::mutex lowstate_mutex_;
  std::chrono::steady_clock::time_point last_lowstate_;
  std::string network_interface_;
};

}  // namespace r1::motion
