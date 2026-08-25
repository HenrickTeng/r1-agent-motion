#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>

#include "unitree/dds_wrapper/robots/g1/g1.h"
#include "unitree/dds_wrapper/robots/r1/r1.h"

namespace {
constexpr std::size_t kRightWristRoll = 9;
constexpr std::array<float, 13> kKp = {50, 50, 40, 40, 30, 50, 50, 40, 40, 30, 50, 15, 15};
constexpr std::array<float, 13> kKd = {2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 1, 1};

float MinimumJerk(float progress) {
  return 10 * std::pow(progress, 3) - 15 * std::pow(progress, 4) + 6 * std::pow(progress, 5);
}

class WristTrial {
 public:
  WristTrial() {
    lowstate_ = std::make_shared<unitree::robot::g1::subscription::LowState>();
    std::cout << "Waiting for rt/lowstate..." << std::endl;
    lowstate_->wait_for_connection();
    armsdk_ = std::make_unique<unitree::robot::r1::publisher::ArmSdk>();
  }

  std::array<float, 13> CurrentPose() const {
    std::array<float, 13> pose{};
    for (std::size_t index = 0; index < pose.size(); ++index) {
      const int joint = static_cast<int>(armsdk_->JOINTS[index]);
      pose[index] = lowstate_->msg_.motor_state().at(joint).q();
    }
    return pose;
  }

  void Enable(const std::array<float, 13>& initial) {
    armsdk_->lock();
    armsdk_->weight(1);
    for (std::size_t index = 0; index < initial.size(); ++index) {
      const int joint = static_cast<int>(armsdk_->JOINTS[index]);
      auto& command = armsdk_->msg_.motor_cmd().at(joint);
      command.q(initial[index]);
      command.kp(kKp[index]);
      command.kd(kKd[index]);
      command.dq(0);
      command.tau(0);
    }
    armsdk_->unlockAndPublish();
  }

  void Move(const std::array<float, 13>& start, const std::array<float, 13>& target,
            float duration_seconds) {
    const auto started = std::chrono::steady_clock::now();
    while (true) {
      const float elapsed = std::chrono::duration<float>(std::chrono::steady_clock::now() - started).count();
      const float progress = std::clamp(elapsed / duration_seconds, 0.0f, 1.0f);
      const float blend = MinimumJerk(progress);
      armsdk_->lock();
      for (std::size_t index = 0; index < start.size(); ++index) {
        const int joint = static_cast<int>(armsdk_->JOINTS[index]);
        armsdk_->msg_.motor_cmd().at(joint).q(start[index] + (target[index] - start[index]) * blend);
      }
      armsdk_->unlockAndPublish();
      int maximum_temperature = 0;
      for (const auto joint : armsdk_->JOINTS) {
        maximum_temperature = std::max(
            maximum_temperature,
            static_cast<int>(lowstate_->msg_.motor_state().at(static_cast<int>(joint)).temperature().at(0)));
      }
      if (maximum_temperature > 70)
        throw std::runtime_error("an ArmSdk motor temperature exceeded 70 C");
      const auto& rpy = lowstate_->msg_.imu_state().rpy();
      if (std::abs(rpy[0]) > 0.35f || std::abs(rpy[1]) > 0.35f)
        throw std::runtime_error("IMU roll/pitch exceeded wrist-trial envelope");
      if (progress >= 1) return;
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
  }

  void Release(float duration_seconds = 1) noexcept {
    const auto started = std::chrono::steady_clock::now();
    while (true) {
      const float elapsed = std::chrono::duration<float>(std::chrono::steady_clock::now() - started).count();
      const float weight = std::clamp(1 - elapsed / duration_seconds, 0.0f, 1.0f);
      armsdk_->lock();
      armsdk_->weight(weight);
      armsdk_->unlockAndPublish();
      if (weight <= 0) return;
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
  }

  bool Run(float offset) {
    const auto initial = CurrentPose();
    auto target = initial;
    target[kRightWristRoll] += offset;
    try {
      Enable(initial);
      std::this_thread::sleep_for(std::chrono::milliseconds(500));
      Move(initial, target, 2);
      std::this_thread::sleep_for(std::chrono::milliseconds(700));
      Move(target, initial, 2);
      Release();
      const float return_error = std::abs(CurrentPose()[kRightWristRoll] - initial[kRightWristRoll]);
      std::cout << "return_error_rad=" << return_error << std::endl;
      return return_error <= 0.05f;
    } catch (const std::exception& error) {
      std::cerr << "trial aborted: " << error.what() << std::endl;
      Release();
      return false;
    }
  }

 private:
  std::shared_ptr<unitree::robot::g1::subscription::LowState> lowstate_;
  std::unique_ptr<unitree::robot::r1::publisher::ArmSdk> armsdk_;
};
}  // namespace

int main(int argc, char const* argv[]) {
  if (argc < 2 || argc > 3) {
    std::cerr << "Usage: " << argv[0] << " networkInterface [small|full]" << std::endl;
    return 1;
  }
  const std::string scale = argc == 3 ? argv[2] : "small";
  const float offset = scale == "small" ? 0.12f : scale == "full" ? 0.35f : -1;
  if (offset < 0) {
    std::cerr << "scale must be small or full" << std::endl;
    return 1;
  }
  std::cout << "Confirm: environment clear, emergency stop in hand, robot stable, "
               "and this right-wrist trial is authorized. Type START: ";
  std::string confirmation;
  std::cin >> confirmation;
  if (confirmation != "START") {
    std::cout << "No motion command sent." << std::endl;
    return 0;
  }
  unitree::robot::ChannelFactory::Instance()->Init(0, argv[1]);
  WristTrial trial;
  return trial.Run(offset) ? 0 : 2;
}
