# PC1 Gateway

The PC1 Gateway is the sole production DDS control boundary. Its deterministic core validates schema versions, installed action IDs, FSM 811 readiness, fresh LowState feedback, operator enable, idempotency, bounded locomotion and cancellation before delegating to a hardware adapter.

The protobuf API defines mutual-TLS RPCs for capabilities, status, package installation, plan validation/execution, cancellation and event streaming. Certificates are deployment secrets and are never stored in Git.

```bash
cmake -S gateway -B build/gateway
cmake --build build/gateway
ctest --test-dir build/gateway --output-on-failure
```

If C++ gRPC development packages are absent, CMake builds a fail-closed executable and the fully testable gateway core. That executable intentionally refuses hardware control. PC1 deployment must supply gRPC, generated protobuf sources, Unitree SDK2 and the deployment adapter before the service is enabled.
