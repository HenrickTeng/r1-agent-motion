---
name: control-unitree-r1
description: Operate or design safe classroom motions for a Unitree R1 through the R1 Agent Motion Teacher Bridge. Use for student voice/text interaction, published gesture composition, bounded locomotion, capability checks, or upper-body motion design; excludes direct DDS, raw joints, full-body generation, dance, jump, bow, squat, and running.
---

# Control Unitree R1

Use the loopback Teacher Bridge as the only tool boundary. Never invoke DDS, SDK examples, hardware-test binaries, Shell commands, `LowCmd`, raw trajectory data, or runtime gains from a student request.

Choose exactly one mode:

- **Execute mode:** Read [references/execute-mode.md](references/execute-mode.md). Converse or compose only actions returned by `robot.list_actions`; validate every `motion-plan/v2` before requesting execution.
- **Design mode:** Read [references/design-mode.md](references/design-mode.md). Produce `motion-design-spec/v1`, compile and simulate revisions, but never request hardware execution or lifecycle approval.

Read [references/safety-and-hardware.md](references/safety-and-hardware.md) before any operator-authorized hardware action or diagnostic. A spoken instruction is never operator authorization.
