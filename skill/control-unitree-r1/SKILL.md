---
name: control-unitree-r1
description: Map spoken or typed Chinese instructions to named Unitree R1 motions and run them over the robot Ethernet. Use when the user wants R1 to wave, salute, speak, turn, or chain classroom gestures; do not invent joints, DDS, or LowCmd.
---

# Control Unitree R1

Laptop on the robot Ethernet talks DDS directly. The model only chooses named actions from `actions.json`.

## Run

```bash
python -m r1_agent --text "请介绍自己，然后挥右手"
python -m r1_agent --text "挥右手然后敬礼" --hardware --interface en5
python -m r1_agent --listen --hardware --interface en5
python -m r1_agent --listen --continuous --hardware --interface en5
```

`--listen` uses R1 ASR (`rt/audio_msg`) and DeepSeek to recover garbled transcripts into catalog atoms. `--hardware` runs TTS, fixed arm motions, and loco. Typed `--text` stays on local rules unless you also pass `--deepseek`. Keys: `DEEPSEEK_API_KEY` or `deepseek_key.txt`.

## Allowed actions

speech: `self_intro`

arm/head: `wrist_wave`, `wrist_wave_left`, `wave_right`, `wave_left`, `hands_forward`, `open_arms`, `salute_right`, `salute_left`, `raise_hand_left`, `raise_hand_right`, `present_left`, `present_right`, `ready_pose`, `small_cheer`, `dual_arm_gesture`, `nod`, `look`, `look_right`, `shake_head`, `listen_left`, `listen_right`, `clap`, `come_here`, `point_left`, `point_right`, `stretch`, `hug`, `akimbo`, `waist_left`, `waist_right`

move/turn: `move_forward_slow`, `move_forward_long`, `move_backward_slow`, `move_backward_long`, `move_left_slow`, `move_right_slow`, `turn_left_10`, `turn_right_10`, `turn_left_20`, `turn_right_20`, `turn_left_45`, `turn_right_45`, `turn_left_90`, `turn_right_90`, `stop_move`

Compositions: 欢迎, 问候学生, 邀请回答, 回答正确, 再试一次, 开始上课, 结束课程, 能力展示, 鼓掌欢迎.

## Rules

- Plan a serial list of catalog atoms for any instruction. Never output joint angles, `LowCmd`, DDS topics, Shell, or Python for the robot.
- Do not add scene-specific actions. Compose existing names; if the catalog cannot cover the request, return no actions.
- Reject 跳舞, 跳跃, 鞠躬, 下蹲, 跑步, 翻滚, and any name not in the catalog. Say it is not in the action library.
- Upper-body and walking are serial, never overlapping.
- If loco `SetVelocity` fails (this firmware has returned `127`), stop the rest of the plan and do not retry.
- After TTS, wait before the next ASR turn so the robot does not hear itself.
