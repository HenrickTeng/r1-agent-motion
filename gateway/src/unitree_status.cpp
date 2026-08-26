#include "unitree_r1_hardware.hpp"

#include <iostream>

int main(int argc, char** argv) {
  if (argc != 2) {
    std::cerr << "usage: r1-unitree-status <network_interface>\n";
    return 2;
  }
  r1::motion::UnitreeR1Hardware hardware(argv[1]);
  const auto status = hardware.ReadStatus();
  std::cout << "connected=" << status.connected << " fsm_id=" << status.fsm_id
            << " fsm_mode=" << status.fsm_mode
            << " lowstate_fresh=" << status.lowstate_fresh;
  if (!status.fault.empty()) std::cout << " fault=" << status.fault;
  std::cout << '\n';
  return status.connected && status.lowstate_fresh ? 0 : 1;
}
