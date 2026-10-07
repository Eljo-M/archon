#include <grpcpp/grpcpp.h>
#include "archon.grpc.pb.h"

#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <mutex>
#include <string>
#include <unordered_map>

// Single-coordinator development service. Cluster failover and durable leases are later milestones.
class Coordinator final : public archon::v1::ClusterCoordinator::CallbackService {
 public:
  explicit Coordinator(std::string token) : token_(std::move(token)) {}

  grpc::ServerUnaryReactor* RegisterNode(grpc::CallbackServerContext* context,
      const archon::v1::NodeInfo* request, archon::v1::RegisterResponse* response) override {
    auto* reactor = context->DefaultReactor();
    if (!authorized(*context)) {
      reactor->Finish({grpc::StatusCode::UNAUTHENTICATED, "Bearer token required"});
      return reactor;
    }
    if (request->node_id().empty() || request->ip_address().empty() || request->cpu_cores() < 1 ||
        request->port() < 1 || request->port() > 65535 || request->gpu_vram_mb() < 0) {
      reactor->Finish({grpc::StatusCode::INVALID_ARGUMENT, "Invalid node capabilities"});
      return reactor;
    }
    {
      std::lock_guard lock(mutex_);
      nodes_[request->node_id()] = Clock::now();
    }
    response->set_accepted(true);
    response->set_cluster_leader_id("archon-cpp-dev-coordinator");
    response->set_term(1);
    reactor->Finish(grpc::Status::OK);
    return reactor;
  }

  grpc::ServerUnaryReactor* SendHeartbeat(grpc::CallbackServerContext* context,
      const archon::v1::HeartbeatRequest* request, archon::v1::HeartbeatResponse* response) override {
    auto* reactor = context->DefaultReactor();
    if (!authorized(*context)) {
      reactor->Finish({grpc::StatusCode::UNAUTHENTICATED, "Bearer token required"});
      return reactor;
    }
    if (!std::isfinite(request->gpu_utilization()) || request->gpu_utilization() < 0 ||
        request->gpu_utilization() > 1 || !std::isfinite(request->memory_usage_mb()) ||
        request->memory_usage_mb() < 0 || request->active_tasks() < 0) {
      reactor->Finish({grpc::StatusCode::INVALID_ARGUMENT, "Invalid heartbeat measurements"});
      return reactor;
    }
    {
      std::lock_guard lock(mutex_);
      const auto found = nodes_.find(request->node_id());
      const auto now = Clock::now();
      const bool live = found != nodes_.end() && now - found->second <= std::chrono::seconds(60);
      response->set_acknowledged(live);
      if (live) found->second = now;
    }
    reactor->Finish(grpc::Status::OK);
    return reactor;
  }

 private:
  using Clock = std::chrono::steady_clock;
  bool authorized(const grpc::CallbackServerContext& context) const {
    const auto found = context.client_metadata().find("authorization");
    if (found == context.client_metadata().end()) return false;
    const auto expected = std::string("Bearer ") + token_;
    const std::string supplied(found->second.data(), found->second.size());
    // Constant-work comparison for equal-length tokens; endpoint is loopback-only.
    if (supplied.size() != expected.size()) return false;
    unsigned char mismatch = 0;
    for (std::size_t i = 0; i < expected.size(); ++i) mismatch |= supplied[i] ^ expected[i];
    return mismatch == 0;
  }
  std::string token_;
  std::mutex mutex_;
  std::unordered_map<std::string, Clock::time_point> nodes_;
};

int main() {
  const char* token = std::getenv("ARCHON_API_TOKEN");
  if (token == nullptr || *token == '\0') {
    std::cerr << "ARCHON_API_TOKEN is required\n";
    return 1;
  }
  Coordinator coordinator(token);
  grpc::ServerBuilder builder;
  builder.AddListeningPort("127.0.0.1:50052", grpc::InsecureServerCredentials());
  builder.RegisterService(&coordinator);
  auto server = builder.BuildAndStart();
  if (!server) return 1;
  std::cout << "Archon C++ coordinator listening on 127.0.0.1:50052\n";
  server->Wait();
}
