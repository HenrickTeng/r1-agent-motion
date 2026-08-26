#include <chrono>
#include <iostream>
#include <map>
#include <memory>
#include <string>
#include <thread>

#include <unitree/robot/channel/channel_factory.hpp>
#include <unitree/robot/r1/loco/r1_loco_client.hpp>

namespace {
struct Command { float vx; float vy; float omega; float duration; };
const std::map<std::string, Command> kCommands = {
    {"move_forward_slow", {0.05f, 0.0f, 0.0f, 0.5f}},
    {"move_backward_slow", {-0.05f, 0.0f, 0.0f, 0.5f}},
    {"move_left_slow", {0.0f, 0.05f, 0.0f, 0.6f}},
    {"move_right_slow", {0.0f, -0.05f, 0.0f, 0.6f}},
    {"turn_left_10", {0.0f, 0.0f, 0.35f, 0.5f}},
    {"turn_right_10", {0.0f, 0.0f, -0.35f, 0.5f}},
    {"turn_left_20", {0.0f, 0.0f, 0.35f, 1.0f}},
    {"turn_right_20", {0.0f, 0.0f, -0.35f, 1.0f}},
};
}  // namespace

int main(int argc, char** argv) {
  if (argc != 3) {
    std::cerr << "Usage: " << argv[0] << " networkInterface action_name\n";
    return 1;
  }
  const auto command = kCommands.find(argv[2]);
  if (command == kCommands.end()) {
    std::cerr << "unknown fixed locomotion action\n";
    return 2;
  }
  std::cout << "Fixed locomotion action " << argv[2] << ". Type START: ";
  std::string confirmation;
  std::cin >> confirmation;
  if (confirmation != "START") {
    std::cout << "No locomotion command sent.\n";
    return 0;
  }
  unitree::robot::ChannelFactory::Instance()->Init(0, argv[1]);
  auto loco = std::make_unique<unitree::robot::r1::LocoClient>();
  loco->Init();
  loco->SetTimeout(2.f);
  const auto& cmd = command->second;
  const int move_result = loco->SetVelocity(cmd.vx, cmd.vy, cmd.omega, cmd.duration);
  std::cerr << "SetVelocity result=" << move_result << "\n";
  if (move_result == 0) {
    std::this_thread::sleep_for(std::chrono::duration<float>(cmd.duration));
  }
  const int stop_result = loco->StopMove();
  std::cerr << "StopMove result=" << stop_result << "\n";
  return move_result == 0 && stop_result == 0 ? 0 : 4;
}
