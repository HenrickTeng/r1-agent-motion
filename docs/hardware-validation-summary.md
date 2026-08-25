# Sanitized hardware validation summary

Date: 2026-08-25. Teacher Ethernet interface: `enp7s0`. Robot endpoints: controller `.161`, PC1 `.164` on the isolated `192.168.123.0/24` network.

- Network: both endpoints responded with 0% packet loss in the recorded four-packet checks.
- FSM: ID 811, mode 0.
- LowState: 35 motor states received; diagnostic was read-only.
- ASR: meaningful Chinese transcript received despite firmware reporting `is_final=false` near confidence 0.5.
- TTS: official local voice RPC returned 0.
- Prior SDK-tree wrist prototype: right wrist +0.35 rad, 1.2 s out/1 s hold/1.2 s return; final feedback approximately 0.00583 rad, zero velocity, 34–35°C. User accepted the hardware path.
- Current repository-owned minimum-jerk wrist binary: built successfully; fresh 0.12/0.35 rad physical regression is pending.

Current implementation-run read-only recheck:

- `.161`: 0% loss, 0.205 ms average; `.164`: 0% loss, 0.423 ms average.
- FSM 811, mode 0; five LowState samples each contained 35 motors.
- Right wrist stayed near 0.0042 rad at 36°C.
- `head_yaw` reported 64°C while other ArmSdk joints reported 32–51°C. No motion followed this observation; the repository-owned trial was tightened to monitor all 13 ArmSdk temperatures with a 70°C hard abort, and cooling/recheck is required before H6.

No new gesture, locomotion, DeepSeek-triggered motion or imported student motion has been physically executed by this implementation run. No hardware-validated tag is created until those staged tests are completed.
