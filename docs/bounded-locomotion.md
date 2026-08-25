# Bounded locomotion

`move_for` is deliberately a velocity-time primitive. It does not estimate or promise travelled distance. The Gateway clamps longitudinal and lateral velocity, rejects durations over two seconds and calls `StopMove` after every step, cancellation, timeout or fault.

`turn_relative` reads yaw from `rt/lowstate`, normalizes wraparound at ±π, applies a proportional command capped at 0.2 rad/s, slows near the target and stops within a 1.5° tolerance or on timeout. The accepted request is at most 30°.

These steps are always sequential with upper-body actions. They remain unavailable for real execution until each forward/backward, lateral and 10°/20°/30° physical trial is separately accepted.
