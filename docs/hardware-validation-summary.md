# Sanitized hardware validation summary

Date: 2026-08-25. Teacher Ethernet interface: `enp7s0`. Robot endpoints: controller `.161`, PC1 `.164` on the isolated `192.168.123.0/24` network.

- Network: both endpoints responded with 0% packet loss in the recorded four-packet checks.
- FSM: ID 811, mode 0.
- LowState: 35 motor states received; diagnostic was read-only.
- ASR: meaningful Chinese transcript received despite firmware reporting `is_final=false` near confidence 0.5.
- TTS: official local voice RPC returned 0.
- Prior SDK-tree wrist prototype: right wrist +0.35 rad, 1.2 s out/1 s hold/1.2 s return; final feedback approximately 0.00583 rad, zero velocity, 34–35°C. User accepted the hardware path.
- Current repository-owned minimum-jerk wrist binary: `+0.12 rad` and `+0.35 rad` physical regressions passed. The supervised voice-triggered `+0.35 rad` run returned within `0.00144 rad` and released ArmSdk normally.

Current implementation-run read-only recheck:

- `.161`: 0% loss, 0.205 ms average; `.164`: 0% loss, 0.423 ms average.
- FSM 811, mode 0; five LowState samples each contained 35 motors.
- Right wrist stayed near 0.0042 rad at 36°C.
- `head_yaw` reported 64°C while other ArmSdk joints reported 32–51°C. No motion followed this observation; the repository-owned trial was tightened to monitor all 13 ArmSdk temperatures with a 70°C hard abort, and cooling/recheck is required before H6.

Validated after a full charge and normal locked-stand startup:

- App head-yaw display and LowState agreed at approximately `0.19°` while the head faced forward. Repeated post-motion LowState samples kept `head_yaw` near `0.003 rad`, with negligible velocity and `42–44°C` temperature.
- R1 ASR recognized self-introduction, forbidden-motion and fixed joint-trial requests. Firmware continued to report `is_final=false` and confidence `0.5`; the local stability fallback accepted the latest meaningful Chinese transcript.
- The local safety Agent replied through R1 TTS, rejected dance plus bow with no plan and no motion, and generated strict one-step MotionPlan v2 payloads for the two authorized trials.
- Right wrist: `+0.12 rad` small trial passed; `+0.35 rad` supervised voice-triggered target trial passed with `0.00144 rad` return error.
- Right shoulder pitch: `-0.07 rad` small trial passed with `0.01817 rad` return error; `-0.20 rad` supervised voice-triggered target trial passed with `0.0122 rad` return error.
- Both target trials used one-shot action allowlists, empty runtime parameters, an operator-authorized session, TTS-before-motion, an internal `START` gate, all-ArmSdk temperature monitoring, IMU monitoring, return-to-initial-pose and smooth ArmSdk release.
- Final post-trial feedback reported right wrist `36°C`, right shoulder pitch `42°C`, head yaw `42°C`, and a maximum ArmSdk temperature of `51°C`. The on-site operator observed normal direction, visible amplitude, stable feet, no abnormal sound and successful return.

These results qualify the repository-owned wrist template and the right-shoulder-pitch single-joint calibration path only. The shoulder trial is not a classroom action, neither trial is automatically `classroom_enabled`, the supervised local trial path is not the production PC1 Gateway, and no DeepSeek-triggered motion, locomotion, generated motion or imported student motion was physically executed. No `v0.2.1-hardware-validated` tag is created until the remaining staged hardware matrix is complete.
