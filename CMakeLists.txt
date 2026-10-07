cmake_minimum_required(VERSION 3.24)
project(archon LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
option(ARCHON_SANITIZERS "Enable address and undefined-behavior sanitizers" OFF)
find_package(Protobuf REQUIRED)
find_package(gRPC CONFIG REQUIRED)
set(GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(MAKE_DIRECTORY "${GENERATED_DIR}")
add_custom_command(
  OUTPUT "${GENERATED_DIR}/archon.pb.cc" "${GENERATED_DIR}/archon.pb.h"
         "${GENERATED_DIR}/archon.grpc.pb.cc" "${GENERATED_DIR}/archon.grpc.pb.h"
  COMMAND protobuf::protoc
  ARGS "--proto_path=${CMAKE_CURRENT_SOURCE_DIR}/proto"
       "--cpp_out=${GENERATED_DIR}" "--grpc_out=${GENERATED_DIR}"
       --plugin=protoc-gen-grpc=$<TARGET_FILE:gRPC::grpc_cpp_plugin>
       "${CMAKE_CURRENT_SOURCE_DIR}/proto/archon.proto"
  DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/proto/archon.proto"
  VERBATIM
)
add_library(archon_proto "${GENERATED_DIR}/archon.pb.cc" "${GENERATED_DIR}/archon.grpc.pb.cc")
target_include_directories(archon_proto PUBLIC "${GENERATED_DIR}")
target_link_libraries(archon_proto PUBLIC protobuf::libprotobuf gRPC::grpc++)
add_executable(archon-coordinator src/gateway/cpp/coordinator.cpp)
target_link_libraries(archon-coordinator PRIVATE archon_proto)
if(ARCHON_SANITIZERS AND CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(archon-coordinator PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
  target_link_options(archon-coordinator PRIVATE -fsanitize=address,undefined)
endif()
