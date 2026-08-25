cmake_minimum_required(VERSION 3.10)
project(r1_agent_motion_hardware_tests)

set(UNITREE_SDK2_DIR "" CACHE PATH "Path to the unitree_sdk2 source tree")
if(NOT UNITREE_SDK2_DIR)
  message(FATAL_ERROR "Set -DUNITREE_SDK2_DIR=/path/to/unitree_sdk2-main")
endif()

add_subdirectory(${UNITREE_SDK2_DIR} unitree_sdk2_build EXCLUDE_FROM_ALL)
add_executable(r1_arm_feedback_test r1_arm_feedback_test.cpp)
target_link_libraries(r1_arm_feedback_test unitree_sdk2 fmt)

add_executable(r1_asr_listener r1_asr_listener.cpp)
target_link_libraries(r1_asr_listener unitree_sdk2 fmt)

add_executable(r1_tts_say r1_tts_say.cpp)
target_link_libraries(r1_tts_say unitree_sdk2 fmt)
