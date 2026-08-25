#include <chrono>
#include <iostream>
#include <memory>
#include <thread>

#include "unitree/dds_wrapper/robots/g1/g1.h"
#include "unitree/dds_wrapper/robots/r1/r1.h"

namespace {

constexpr std::array<const char*, 13> kArmJointNames = {
    "left_shoulder_pitch", "left_shoulder_roll", "left_shoulder_yaw",
    "left_elbow", "left_wrist_roll", "right_shoulder_pitch",
    "right_shoulder_roll", "right_shoulder_yaw", "right_elbow",
    "right_wrist_roll", "waist_yaw", "head_pitch", "head_yaw"};

void PrintArmFeedback(const unitree_hg::msg::dds_::LowState_& lowstate) {
  for (size_t index = 0;
       index < unitree::robot::r1::publisher::ArmSdk::JOINTS.size(); ++index) {
    const auto joint_index = static_cast<int>(
        unitree::robot::r1::publisher::ArmSdk::JOINTS[index]);
    const auto& motor = lowstate.motor_state().at(joint_index);
    std::cout << "  " << kArmJointNames[index] << " (index " << joint_index
              << "): q_rad=" << motor.q() << " dq_radps=" << motor.dq()
              << " tau_est_nm=" << motor.tau_est()
              << " temperature=" << motor.temperature().at(0) << std::endl;
  }
}

}  // namespace

int main(int argc, char const* argv[]) {
  if (argc != 2) {
    std::cerr << "Usage: " << argv[0] << " networkInterface" << std::endl;
    return 1;
  }

  unitree::robot::ChannelFactory::Instance()->Init(0, argv[1]);
  auto lowstate = std::make_shared<unitree::robot::g1::subscription::LowState>();
  std::cout << "Waiting for read-only rt/lowstate feedback..." << std::endl;
  lowstate->wait_for_connection();

  for (int sample = 1; sample <= 5; ++sample) {
    std::cout << "sample=" << sample
              << " motor_count=" << lowstate->msg_.motor_state().size()
              << std::endl;
    PrintArmFeedback(lowstate->msg_);
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
  }

  std::cout << "Read-only arm feedback test passed; no ArmSdk publisher was created."
            << std::endl;
  return 0;
}
