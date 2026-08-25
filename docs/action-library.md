# Classroom action library

The registry contains 36 classroom actions: 19 upper-body/head or semantic gesture entries, 9 classroom compositions, and 8 bounded locomotion macros. Registration and implementation are intentionally separate. `wrist_wave` carries the accepted 2026-08-25 physical return-and-release evidence and remains unpublished until a teacher performs the explicit registration transition. Every new entry begins in `draft` because its joints or locomotion direction still require individual calibration, authoritative simulation and staged hardware validation.

Templates are relative to the measured current pose, use the fixed 13-joint ArmSdk order, return to the initial pose and never run concurrently with locomotion. Their numeric values are conservative design inputs, not authorization to send them to hardware.

The lower-body set is intentionally limited to fixed semantic macros: slow forward/backward motion, slow left/right lateral motion, and IMU-closed-loop left/right turns of 10° or 20°. These expand only to already bounded `move_for` or `turn_relative` plan steps and expose no student-controlled speed, duration or angle. There is no squat, kick, marching, one-leg support, bow, run, stand-mode transition or arm-and-leg concurrency.
