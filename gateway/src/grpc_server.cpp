#include "gateway_core.hpp"
#ifdef R1_GATEWAY_USE_UNITREE
#include "unitree_r1_hardware.hpp"
#endif
#include "r1_gateway.grpc.pb.h"

#include <grpcpp/grpcpp.h>

#include <chrono>
#include <condition_variable>
#include <fstream>
#include <iostream>
#include <map>
#include <mutex>
#include <stdexcept>

namespace proto = r1::motion::gateway::v1;

namespace {
std::string ReadFile(const std::string& path) {
  std::ifstream input(path);
  if (!input) throw std::runtime_error("cannot read TLS file: " + path);
  return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}

class RefusingDeploymentHardware final : public r1::motion::RobotHardware {
 public:
  r1::motion::RobotStatus ReadStatus() override {
    r1::motion::RobotStatus status;
    status.fault = "Unitree deployment adapter is not configured";
    return status;
  }
  bool ExecuteInstalledAction(const std::string&, std::atomic_bool&) override { return false; }
  bool MoveFor(double, double, double, std::atomic_bool&) override { return false; }
  bool TurnRelative(double, double, std::atomic_bool&) override { return false; }
  void StopAndRelease() noexcept override {}
};

struct StoredEvent {
  std::string type;
  int step_index;
  std::string detail;
  long long time_ms;
};

class EventStore {
 public:
  void Add(const std::string& execution_id, const std::string& type, int step_index,
           const std::string& detail) {
    const auto time = std::chrono::duration_cast<std::chrono::milliseconds>(
                          std::chrono::steady_clock::now().time_since_epoch())
                          .count();
    {
      std::lock_guard<std::mutex> lock(mutex_);
      events_[execution_id].push_back({type, step_index, detail, time});
    }
    changed_.notify_all();
  }

  bool Wait(const std::string& execution_id, std::size_t index, StoredEvent& event,
            std::chrono::milliseconds timeout) {
    std::unique_lock<std::mutex> lock(mutex_);
    changed_.wait_for(lock, timeout, [&] { return events_[execution_id].size() > index; });
    if (events_[execution_id].size() <= index) return false;
    event = events_[execution_id][index];
    return true;
  }

 private:
  std::mutex mutex_;
  std::condition_variable changed_;
  std::map<std::string, std::vector<StoredEvent>> events_;
};

r1::motion::MotionPlan ConvertPlan(const proto::MotionPlan& source) {
  r1::motion::MotionPlan plan;
  plan.schema_version = source.schema_version();
  plan.plan_id = source.plan_id();
  plan.require_operator_enable = source.require_operator_enable();
  for (const auto& source_step : source.steps()) {
    if (source_step.has_say()) {
      plan.steps.emplace_back(r1::motion::SayStep{source_step.say().text()});
    } else if (source_step.has_action()) {
      plan.steps.emplace_back(r1::motion::ActionStep{source_step.action().action()});
    } else if (source_step.has_move_for()) {
      plan.steps.emplace_back(r1::motion::MoveForStep{
          source_step.move_for().vx_mps(), source_step.move_for().vy_mps(),
          source_step.move_for().duration_s()});
    } else if (source_step.has_turn_relative()) {
      plan.steps.emplace_back(
          r1::motion::TurnRelativeStep{source_step.turn_relative().angle_deg()});
    } else if (source_step.has_wait()) {
      plan.steps.emplace_back(r1::motion::WaitStep{source_step.wait().duration_s()});
    }
  }
  return plan;
}

class Service final : public proto::R1Gateway::Service {
 public:
  explicit Service(r1::motion::GatewayCore& core) : core_(core) {}

  grpc::Status GetCapabilities(grpc::ServerContext*, const proto::Empty*,
                               proto::Capabilities* response) override {
    response->set_gateway_version("0.1.0");
    for (const auto* type : {"say", "action", "move_for", "turn_relative", "wait"})
      response->add_plan_step_types(type);
    response->set_max_vx_mps(0.5);
    response->set_max_vy_mps(0.10);
    response->set_max_move_duration_s(2);
    response->set_max_turn_angle_deg(30);
    response->set_max_turn_rate_rad_s(0.2);
    return grpc::Status::OK;
  }

  grpc::Status GetStatus(grpc::ServerContext*, const proto::Empty*,
                         proto::RobotStatus* response) override {
    const auto status = core_.Status();
    response->set_connected(status.connected);
    response->set_fsm_id(status.fsm_id);
    response->set_fsm_mode(status.fsm_mode);
    response->set_lowstate_fresh(status.lowstate_fresh);
    response->set_executing(status.executing);
    response->set_execution_id(status.execution_id);
    response->set_fault(status.fault);
    return grpc::Status::OK;
  }

  grpc::Status InstallMotionPackage(grpc::ServerContext*,
                                    const proto::InstallMotionPackageRequest*,
                                    proto::InstallMotionPackageResponse* response) override {
    response->set_installed(false);
    response->set_error("C++ package verifier and trajectory store are not configured");
    return grpc::Status::OK;
  }

  grpc::Status ValidatePlan(grpc::ServerContext*, const proto::MotionPlan* request,
                            proto::ValidationResult* response) override {
    const auto result = core_.Validate(ConvertPlan(*request));
    response->set_valid(result.valid);
    for (const auto& error : result.errors) response->add_errors(error);
    return grpc::Status::OK;
  }

  grpc::Status ExecutePlan(grpc::ServerContext*, const proto::ExecutePlanRequest* request,
                           proto::ExecutionHandle* response) override {
    try {
      auto plan = ConvertPlan(request->plan());
      const std::string expected_execution_id = "exec-" + plan.plan_id;
      const auto execution_id = core_.Execute(
          plan, request->idempotency_key(),
          request->operator_enabled(),
          [this, expected_execution_id](const std::string& type, int step,
                                        const std::string& detail) {
            events_.Add(expected_execution_id, type, step, detail);
          });
      response->set_execution_id(execution_id);
      return grpc::Status::OK;
    } catch (const std::exception& error) {
      return grpc::Status(grpc::StatusCode::FAILED_PRECONDITION, error.what());
    }
  }

  grpc::Status CancelExecution(grpc::ServerContext*,
                               const proto::CancelExecutionRequest* request,
                               proto::CancelExecutionResponse* response) override {
    response->set_cancelled(core_.Cancel(request->execution_id()));
    return grpc::Status::OK;
  }

  grpc::Status StreamExecutionEvents(grpc::ServerContext* context,
                                     const proto::ExecutionHandle* request,
                                     grpc::ServerWriter<proto::ExecutionEvent>* writer) override {
    for (std::size_t index = 0; !context->IsCancelled(); ++index) {
      StoredEvent stored;
      if (!events_.Wait(request->execution_id(), index, stored, std::chrono::seconds(1)))
        continue;
      proto::ExecutionEvent event;
      event.set_execution_id(request->execution_id());
      event.set_type(stored.type);
      event.set_step_index(stored.step_index);
      event.set_detail(stored.detail);
      event.set_monotonic_time_ms(stored.time_ms);
      if (!writer->Write(event)) break;
      if (stored.type == "completed" || stored.type == "cancelled" || stored.type == "failed")
        break;
    }
    return grpc::Status::OK;
  }

 private:
  r1::motion::GatewayCore& core_;
  EventStore events_;
};
}  // namespace

int main(int argc, char** argv) {
  if (argc != 3 && argc != 4) {
    std::cerr << "Usage: " << argv[0] << " listenAddress tlsDirectory [networkInterface]\n";
    return 1;
  }
#ifdef R1_GATEWAY_USE_UNITREE
  if (argc != 4) {
    std::cerr << "Unitree build requires networkInterface\n";
    return 1;
  }
#endif
  try {
    grpc::SslServerCredentialsOptions tls;
    tls.pem_root_certs = ReadFile(std::string(argv[2]) + "/teacher-ca.pem");
    tls.pem_key_cert_pairs.push_back({ReadFile(std::string(argv[2]) + "/server-key.pem"),
                                      ReadFile(std::string(argv[2]) + "/server-cert.pem")});
    tls.client_certificate_request =
        GRPC_SSL_REQUEST_AND_REQUIRE_CLIENT_CERTIFICATE_AND_VERIFY;
#ifdef R1_GATEWAY_USE_UNITREE
    r1::motion::UnitreeR1Hardware hardware(argv[3]);
#else
    RefusingDeploymentHardware hardware;
#endif
    r1::motion::GatewayCore core(hardware);
    Service service(core);
    grpc::ServerBuilder builder;
    builder.AddListeningPort(argv[1], grpc::SslServerCredentials(tls));
    builder.RegisterService(&service);
    auto server = builder.BuildAndStart();
    if (!server) throw std::runtime_error("failed to bind gRPC server");
    std::cout << "R1 Gateway mTLS server listening on " << argv[1] << std::endl;
    server->Wait();
  } catch (const std::exception& error) {
    std::cerr << error.what() << std::endl;
    return 2;
  }
}
