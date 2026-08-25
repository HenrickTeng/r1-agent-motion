# Safety and hardware gates

Only the PC1 Gateway may communicate with Unitree control APIs. `rt/lowstate` is read-only feedback; its absence or staleness blocks execution. Motion requires FSM 811, fresh feedback, healthy communication/temperature/IMU, an enabled teacher session, and physical supervision.

Without a harness, each new joint and template starts at the scaled small-amplitude trial. The operator must confirm a clear environment, emergency stop in hand, robot stable, and permission for that named test. Never combine upper-body motion and locomotion, and never test anything outside `classroom-upper-v1`.

The tested ASR firmware can keep `is_final=false`; use the latest meaningful transcript after 1.5 seconds of silence with confidence at least 0.45. Pause listening while R1 TTS speaks to avoid self-echo. Send only recognized text—not raw audio—to DeepSeek.
