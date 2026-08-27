#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <iostream>
#include <mutex>

#include <unitree/idl/ros2/String_.hpp>
#include <unitree/robot/channel/channel_factory.hpp>
#include <unitree/robot/channel/channel_subscriber.hpp>

namespace {

std::mutex message_mutex;
std::condition_variable message_condition;
bool message_received = false;
std::chrono::steady_clock::time_point last_message_time;

void HandleAsrMessage(const void* raw_message) {
  const auto* message = static_cast<const std_msgs::msg::dds_::String_*>(raw_message);
  const std::string data = message->data();
  std::cout << data << std::endl;
  const bool is_final = data.find("\"is_final\":true") != std::string::npos ||
                        data.find("\"is_final\":1") != std::string::npos;
  const bool has_speech = data.find("\"text\":\"。\"") == std::string::npos &&
                          data.find("<|nospeech|>") == std::string::npos;
  if (!is_final && !has_speech) {
    return;
  }
  {
    std::lock_guard<std::mutex> lock(message_mutex);
    message_received = true;
    last_message_time = std::chrono::steady_clock::now();
  }
  message_condition.notify_one();
}

}  // namespace

int main(int argc, char const* argv[]) {
  if (argc < 2 || argc > 3) {
    std::cerr << "Usage: " << argv[0] << " networkInterface [timeoutSeconds]"
              << std::endl;
    return 1;
  }

  const int timeout_seconds = argc == 3 ? std::atoi(argv[2]) : 30;
  if (timeout_seconds < 1 || timeout_seconds > 300) {
    std::cerr << "timeoutSeconds must be between 1 and 300" << std::endl;
    return 1;
  }

  unitree::robot::ChannelFactory::Instance()->Init(0, argv[1]);
  unitree::robot::ChannelSubscriber<std_msgs::msg::dds_::String_> subscriber(
      "rt/audio_msg");
  subscriber.InitChannel(HandleAsrMessage);

  std::cerr << "Listening read-only on rt/audio_msg for " << timeout_seconds
            << " seconds..." << std::endl;
  const auto deadline = std::chrono::steady_clock::now() +
                        std::chrono::seconds(timeout_seconds);
  std::unique_lock<std::mutex> lock(message_mutex);
  while (std::chrono::steady_clock::now() < deadline) {
    const auto settled_at = message_received
                                ? last_message_time + std::chrono::milliseconds(1500)
                                : deadline;
    message_condition.wait_until(lock, std::min(deadline, settled_at));
    if (message_received &&
        std::chrono::steady_clock::now() >=
            last_message_time + std::chrono::milliseconds(1500)) {
      return 0;
    }
  }
  std::cerr << "ASR timeout: enable microphone wake mode using the R1 app or remote."
            << std::endl;
  return 2;
}
