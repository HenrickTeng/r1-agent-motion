# Architecture and trust boundaries

The public platform edits and simulates motions, then manually exports `.r1motion`. The teacher computer verifies every hash, reruns MuJoCo, records approvals and hosts DeepSeek plus the loopback-only Teacher Bridge. PC1 hosts the mutual-TLS deterministic Gateway on the isolated robot Ethernet. Only Gateway may touch Unitree RPC/DDS.

Cross-component objects are strict JSON Schema 2020-12 contracts. Agent plans contain semantic step types only; packages carry precompiled relative trajectories; the Gateway accepts only installed IDs and bounded locomotion. Students, DeepSeek, browsers and public services have no route that accepts `LowCmd`, arbitrary DDS topics, gains, joint arrays, Shell or code.

The checked-in Gateway core and protobuf API build without C++ gRPC packages in fail-closed mode. PC1 deployment must install protobuf/gRPC development/runtime packages, generate the transport stubs, configure pinned teacher and server certificates, and link the Unitree adapter. The fail-closed desktop binary is not a robot controller.
