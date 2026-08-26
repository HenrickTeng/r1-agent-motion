#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <iostream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "unitree/dds_wrapper/robots/g1/g1.h"
#include "unitree/dds_wrapper/robots/r1/r1.h"

namespace {
using Pose = std::array<float, 13>;
struct Keyframe { float duration; Pose offsets; float hold; };
using Motion = std::vector<Keyframe>;

constexpr std::size_t LSP=0, LSR=1, LSY=2, LE=3, LWR=4;
constexpr std::size_t RSP=5, RSR=6, RSY=7, RE=8, RWR=9, WY=10, HP=11, HY=12;
constexpr std::array<float,13> KP={50,50,40,40,30,50,50,40,40,30,50,15,15};
constexpr std::array<float,13> KD={2,2,2,2,2,2,2,2,2,2,3,1,1};

Pose O(std::initializer_list<std::pair<std::size_t,float>> values) {
  Pose result{}; for (auto [index,value] : values) result[index]=value; return result;
}

const std::map<std::string, Motion> kMotions = {
  {"wrist_wave", {{2.0f,O({{RWR,0.35f}}),1.0f}}},
  {"wrist_wave_left", {{2.0f,O({{LWR,-0.30f}}),0.7f}}},
  {"wave_left", {{2.0f,O({{LSP,-0.16f},{LE,0.25f}}),0.2f},{1.0f,O({{LSP,-0.16f},{LE,0.25f},{LWR,0.25f}}),0.7f}}},
  {"wave_right", {{2.0f,O({{RSP,-0.16f},{RE,0.25f}}),0.2f},{1.0f,O({{RSP,-0.16f},{RE,0.25f},{RWR,0.25f}}),0.7f}}},
  {"raise_hand_left", {{2.5f,O({{LSP,-0.20f},{LSR,0.12f},{LE,0.20f}}),1.0f}}},
  {"raise_hand_right", {{2.5f,O({{RSP,-0.20f},{RSR,-0.12f},{RE,0.20f}}),1.0f}}},
  {"salute_left", {{2.5f,O({{LSP,-0.18f},{LSR,0.10f},{LE,0.28f}}),1.0f}}},
  {"salute_right", {{2.5f,O({{RSP,-0.18f},{RSR,-0.10f},{RE,0.28f}}),1.0f}}},
  {"open_arms", {{2.5f,O({{LSR,0.14f},{RSR,-0.14f}}),1.0f}}},
  {"nod", {{1.5f,O({{HP,0.10f}}),0.2f},{1.0f,O({{HP,-0.06f}}),0.4f}}},
  {"look", {{1.8f,O({{HY,0.15f}}),0.5f}}},
  {"shake_head", {{1.5f,O({{HY,0.12f}}),0.2f},{1.0f,O({{HY,-0.12f}}),0.4f}}},
  {"listen_left", {{1.8f,O({{HY,0.15f}}),1.0f}}},
  {"listen_right", {{1.8f,O({{HY,-0.15f}}),1.0f}}},
  {"present_left", {{2.2f,O({{LSP,-0.12f},{LSR,0.10f},{LE,0.15f}}),1.0f}}},
  {"present_right", {{2.2f,O({{RSP,-0.12f},{RSR,-0.10f},{RE,0.15f}}),1.0f}}},
  {"hands_forward", {{2.3f,O({{LSP,-0.12f},{RSP,-0.12f},{LE,0.12f},{RE,0.12f}}),0.8f}}},
  {"ready_pose", {{1.5f,O({}),0.3f}}},
  {"small_cheer", {{2.5f,O({{LSP,-0.16f},{RSP,-0.16f},{LE,0.20f},{RE,0.20f}}),0.7f}}},
  {"dual_arm_gesture", {{2.0f,O({{LSP,0.36f},{RSP,-0.36f}}),0.6f},{1.5f,O({{LSP,0.36f},{RSP,-0.36f},{LWR,0.72f},{RWR,-0.72f}}),0.8f}}},
};

float Blend(float x) { return 10*std::pow(x,3)-15*std::pow(x,4)+6*std::pow(x,5); }

class Runner {
 public:
  Runner() {
    state_=std::make_shared<unitree::robot::g1::subscription::LowState>();
    state_->wait_for_connection();
    arm_=std::make_unique<unitree::robot::r1::publisher::ArmSdk>();
  }
  Pose Current() const { Pose p{}; for(size_t i=0;i<13;++i)p[i]=state_->msg_.motor_state().at(static_cast<int>(arm_->JOINTS[i])).q(); return p; }
  void Check() const {
    for(auto joint:arm_->JOINTS) if(state_->msg_.motor_state().at(static_cast<int>(joint)).temperature().at(0)>70) throw std::runtime_error("temperature exceeded 70 C");
    const auto&r=state_->msg_.imu_state().rpy(); if(std::abs(r[0])>0.35f||std::abs(r[1])>0.35f) throw std::runtime_error("IMU envelope exceeded");
  }
  void Enable(const Pose&p) { arm_->lock(); arm_->weight(1); for(size_t i=0;i<13;++i){auto&c=arm_->msg_.motor_cmd().at(static_cast<int>(arm_->JOINTS[i]));c.q(p[i]);c.kp(KP[i]);c.kd(KD[i]);c.dq(0);c.tau(0);} arm_->unlockAndPublish(); }
  void Move(const Pose&a,const Pose&b,float seconds) { auto t=std::chrono::steady_clock::now(); while(true){float x=std::clamp(std::chrono::duration<float>(std::chrono::steady_clock::now()-t).count()/seconds,0.f,1.f);float s=Blend(x);arm_->lock();for(size_t i=0;i<13;++i)arm_->msg_.motor_cmd().at(static_cast<int>(arm_->JOINTS[i])).q(a[i]+(b[i]-a[i])*s);arm_->unlockAndPublish();Check();if(x>=1)return;std::this_thread::sleep_for(std::chrono::milliseconds(10));} }
  void Release(){auto t=std::chrono::steady_clock::now();while(true){float w=std::clamp(1-std::chrono::duration<float>(std::chrono::steady_clock::now()-t).count(),0.f,1.f);arm_->lock();arm_->weight(w);arm_->unlockAndPublish();if(w<=0)return;std::this_thread::sleep_for(std::chrono::milliseconds(10));}}
  bool Run(const Motion&m){Pose initial=Current(), previous=initial;try{Check();Enable(initial);for(const auto&k:m){Pose target=initial;for(size_t i=0;i<13;++i)target[i]+=k.offsets[i];Move(previous,target,k.duration);std::this_thread::sleep_for(std::chrono::duration<float>(k.hold));previous=target;}Move(previous,initial,2.0f);Release();float e=0;auto end=Current();for(size_t i=0;i<13;++i)e=std::max(e,std::abs(end[i]-initial[i]));std::cout<<"return_error_rad="<<e<<'\n';return e<=0.06f;}catch(const std::exception&e){std::cerr<<"aborted: "<<e.what()<<'\n';Release();return false;}}
 private: std::shared_ptr<unitree::robot::g1::subscription::LowState> state_; std::unique_ptr<unitree::robot::r1::publisher::ArmSdk> arm_;
};
}

int main(int argc,char**argv){
  if(argc!=3){std::cerr<<"Usage: "<<argv[0]<<" networkInterface action_name\n";return 1;}
  auto it=kMotions.find(argv[2]);if(it==kMotions.end()){std::cerr<<"unknown fixed action\n";return 2;}
  std::cout<<"Fixed experimental action "<<argv[2]<<". Type START: ";std::string confirm;std::cin>>confirm;if(confirm!="START"){std::cout<<"No motion command sent.\n";return 0;}
  unitree::robot::ChannelFactory::Instance()->Init(0,argv[1]);Runner runner;return runner.Run(it->second)?0:3;
}
