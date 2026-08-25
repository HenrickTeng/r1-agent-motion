#include <cstdlib>
#include <iostream>
#include <string>

#include <unitree/robot/channel/channel_factory.hpp>
#include <unitree/robot/r1/audio/audio_client.hpp>

int main(int argc, char const* argv[]) {
  if (argc < 3 || argc > 4) {
    std::cerr << "Usage: " << argv[0]
              << " networkInterface text [speakerId: 0=Chinese, 1=English]"
              << std::endl;
    return 1;
  }

  const std::string text = argv[2];
  const int speaker_id = argc == 4 ? std::atoi(argv[3]) : 0;
  if (text.empty() || text.size() > 600) {
    std::cerr << "TTS text must contain 1 to 600 UTF-8 bytes" << std::endl;
    return 1;
  }
  if (speaker_id != 0 && speaker_id != 1) {
    std::cerr << "speakerId must be 0 or 1" << std::endl;
    return 1;
  }

  unitree::robot::ChannelFactory::Instance()->Init(0, argv[1]);
  unitree::robot::r1::AudioClient client;
  client.Init();
  client.SetTimeout(10.0f);
  const int32_t result = client.TtsMaker(text, speaker_id);
  std::cout << "tts_return_code=" << result << std::endl;
  return result == 0 ? 0 : 2;
}
