#include "unitree_r1_hardware.hpp"

#include <atomic>
#include <iostream>
#include <map>
#include <string>

namespace {
struct Command { bool turn; double first; double second; double duration; };
const std::map<std::string, Command> kCommands = {
    {"move_forward_slow", {false, 0.5, 0.0, 2.0}},
    {"move_backward_slow", {false, -0.50, 0.0, 2.0}},
    {"move_left_slow", {false, 0.0, 0.05, 0.60}},
    {"move_right_slow", {false, 0.0, -0.05, 0.60}},
    {"turn_left_10", {true, 10.0, 0.0, 0.0}},
    {"turn_right_10", {true, -10.0, 0.0, 0.0}},
    {"turn_left_20", {true, 20.0, 0.0, 0.0}},
    {"turn_right_20", {true, -20.0, 0.0, 0.0}},
    {"turn_left_rpc", {true, 0.60, 0.0, 1.0}},
    {"turn_right_rpc", {true, -0.60, 0.0, 1.0}},
};
}

int main(int argc, char** argv) {
  if (argc != 3) {
    std::cerr << "usage: r1-fixed-locomotion networkInterface action_name\n";
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
  r1::motion::UnitreeR1Hardware hardware(argv[1]);
  const auto status = hardware.ReadStatus();
  std::cout << "status connected=" << status.connected << " fsm_id=" << status.fsm_id
            << " fsm_mode=" << status.fsm_mode
            << " lowstate_fresh=" << status.lowstate_fresh
            << " fault=" << status.fault << '\n';
  if (!status.connected || status.fsm_id != 811 || !status.lowstate_fresh) {
    std::cerr << "robot is not ready in FSM 811 with fresh LowState\n";
    return 3;
  }
  std::atomic_bool cancelled{false};
  bool passed = command->second.turn
      ? (command->first == "turn_left_rpc" || command->first == "turn_right_rpc"
             ? hardware.TurnFor(command->second.first, command->second.duration, cancelled, 3, 1.0)
             : hardware.TurnRelative(command->second.first, 0.2, cancelled))
      : hardware.MoveFor(command->second.first, command->second.second,
                         command->second.duration, cancelled);
  hardware.StopAndRelease();
  std::cout << (passed ? "completed_and_stopped\n" : "failed_and_stopped\n");
  return passed ? 0 : 4;
}
