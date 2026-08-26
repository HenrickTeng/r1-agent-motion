cmake_minimum_required(VERSION 3.16)
project(r1_pc1_gateway VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
option(R1_GATEWAY_BUILD_GRPC "Build the gRPC transport when development packages exist" ON)
option(R1_GATEWAY_BUILD_TESTS "Build gateway unit tests" ON)
option(R1_GATEWAY_BUILD_UNITREE "Build the R1 Unitree SDK hardware adapter" OFF)

add_library(r1_gateway_core src/gateway_core.cpp src/locomotion_policy.cpp)
target_include_directories(r1_gateway_core PUBLIC src)
target_compile_options(r1_gateway_core PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(r1_gateway_core PUBLIC pthread)

add_executable(r1-gateway src/main.cpp)
target_link_libraries(r1-gateway PRIVATE r1_gateway_core)

if(R1_GATEWAY_BUILD_UNITREE)
  if(NOT DEFINED UNITREE_SDK2_DIR)
    set(UNITREE_SDK2_DIR "$ENV{UNITREE_SDK2_DIR}")
  endif()
  if(NOT UNITREE_SDK2_DIR OR NOT EXISTS "${UNITREE_SDK2_DIR}/include/unitree/robot/r1/loco/r1_loco_client.hpp")
    message(FATAL_ERROR "R1_GATEWAY_BUILD_UNITREE requires UNITREE_SDK2_DIR")
  endif()
  add_library(r1_unitree_hardware src/unitree_r1_hardware.cpp)
  target_include_directories(r1_unitree_hardware PUBLIC
    "${UNITREE_SDK2_DIR}/include"
    "${UNITREE_SDK2_DIR}/thirdparty/include"
    "${UNITREE_SDK2_DIR}/thirdparty/include/ddscxx")
  target_link_libraries(r1_unitree_hardware PRIVATE r1_gateway_core
    "${UNITREE_SDK2_DIR}/lib/x86_64/libunitree_sdk2.a"
    "${UNITREE_SDK2_DIR}/thirdparty/lib/x86_64/libddscxx.so"
    "${UNITREE_SDK2_DIR}/thirdparty/lib/x86_64/libddsc.so"
    spdlog fmt)
  target_compile_definitions(r1_unitree_hardware PRIVATE R1_UNITREE_SDK_ENABLED=1)
  add_executable(r1-unitree-status src/unitree_status.cpp)
  target_link_libraries(r1-unitree-status PRIVATE r1_unitree_hardware)
  add_executable(r1-fixed-locomotion src/fixed_locomotion.cpp)
  target_link_libraries(r1-fixed-locomotion PRIVATE r1_unitree_hardware)
endif()

if(R1_GATEWAY_BUILD_GRPC)
  find_package(Protobuf QUIET)
  find_package(gRPC QUIET)
  if(Protobuf_FOUND AND gRPC_FOUND)
    message(STATUS "gRPC found; deployment transport generation is enabled")
    set(PROTO_FILE ${CMAKE_CURRENT_SOURCE_DIR}/proto/r1_gateway.proto)
    set(PROTO_OUTPUT_DIR ${CMAKE_CURRENT_BINARY_DIR}/generated)
    file(MAKE_DIRECTORY ${PROTO_OUTPUT_DIR})
    add_custom_command(
      OUTPUT ${PROTO_OUTPUT_DIR}/r1_gateway.pb.cc ${PROTO_OUTPUT_DIR}/r1_gateway.pb.h
             ${PROTO_OUTPUT_DIR}/r1_gateway.grpc.pb.cc ${PROTO_OUTPUT_DIR}/r1_gateway.grpc.pb.h
      COMMAND protobuf::protoc
      ARGS --proto_path=${CMAKE_CURRENT_SOURCE_DIR}/proto
           --cpp_out=${PROTO_OUTPUT_DIR}
           --grpc_out=${PROTO_OUTPUT_DIR}
           --plugin=protoc-gen-grpc=$<TARGET_FILE:gRPC::grpc_cpp_plugin>
           ${PROTO_FILE}
      DEPENDS ${PROTO_FILE})
    add_library(r1_gateway_proto
      ${PROTO_OUTPUT_DIR}/r1_gateway.pb.cc
      ${PROTO_OUTPUT_DIR}/r1_gateway.grpc.pb.cc)
    target_include_directories(r1_gateway_proto PUBLIC ${PROTO_OUTPUT_DIR})
    target_link_libraries(r1_gateway_proto PUBLIC protobuf::libprotobuf gRPC::grpc++)
    add_executable(r1-gateway-grpc src/grpc_server.cpp)
    target_link_libraries(r1-gateway-grpc PRIVATE r1_gateway_core r1_gateway_proto gRPC::grpc++)
    if(R1_GATEWAY_BUILD_UNITREE)
      target_link_libraries(r1-gateway-grpc PRIVATE r1_unitree_hardware)
      target_include_directories(r1-gateway-grpc PRIVATE "${UNITREE_SDK2_DIR}/include")
      target_compile_definitions(r1-gateway-grpc PRIVATE R1_GATEWAY_USE_UNITREE=1)
    endif()
  else()
    message(WARNING "gRPC C++ development packages not found; building fail-closed core only")
  endif()
endif()

if(R1_GATEWAY_BUILD_TESTS)
  enable_testing()
  find_package(GTest REQUIRED)
  add_executable(r1_gateway_core_test tests/gateway_core_test.cpp)
  target_link_libraries(r1_gateway_core_test PRIVATE r1_gateway_core GTest::gtest_main)
  add_executable(r1_locomotion_policy_test tests/locomotion_policy_test.cpp)
  target_link_libraries(r1_locomotion_policy_test PRIVATE r1_gateway_core GTest::gtest_main)
  include(GoogleTest)
  gtest_discover_tests(r1_gateway_core_test)
  gtest_discover_tests(r1_locomotion_policy_test)
endif()
