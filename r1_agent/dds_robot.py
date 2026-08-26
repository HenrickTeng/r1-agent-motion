from __future__ import annotations

import json
import time

from r1_agent.asr import select_transcript
from r1_agent.catalog import Action

JOINTS = (15, 16, 17, 18, 19, 22, 23, 24, 25, 26, 13, 29, 30)
KP = (50, 50, 40, 40, 30, 50, 50, 40, 40, 30, 50, 15, 15)
KD = (2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 1, 1)
LSP, LSR, LSY, LE, LWR = 0, 1, 2, 3, 4
RSP, RSR, RSY, RE, RWR = 5, 6, 7, 8, 9
WY, HP, HY = 10, 11, 12


def _offsets(**joints: float) -> tuple[float, ...]:
    pose = [0.0] * 13
    for name, value in joints.items():
        pose[{"LSP": LSP, "LSR": LSR, "LSY": LSY, "LE": LE, "LWR": LWR, "RSP": RSP, "RSR": RSR, "RSY": RSY, "RE": RE, "RWR": RWR, "WY": WY, "HP": HP, "HY": HY}[name]] = value
    return tuple(pose)


MOTIONS: dict[str, list[tuple[float, tuple[float, ...], float]]] = {
    "wrist_wave": [
        (1.2, _offsets(RWR=0.55), 0.05),
        (0.45, _offsets(RWR=-0.45), 0.05),
        (0.45, _offsets(RWR=0.55), 0.2),
    ],
    "wrist_wave_left": [
        (1.2, _offsets(LWR=-0.55), 0.05),
        (0.45, _offsets(LWR=0.45), 0.05),
        (0.45, _offsets(LWR=-0.55), 0.2),
    ],
    "wave_left": [
        (1.6, _offsets(LSP=-0.50, LSR=0.20, LE=0.48), 0.1),
        (0.5, _offsets(LSP=-0.50, LSR=0.20, LE=0.48, LWR=0.65), 0.05),
        (0.5, _offsets(LSP=-0.50, LSR=0.20, LE=0.48, LWR=-0.45), 0.05),
        (0.5, _offsets(LSP=-0.50, LSR=0.20, LE=0.48, LWR=0.65), 0.2),
    ],
    "wave_right": [
        (1.6, _offsets(RSP=-0.50, RSR=-0.20, RE=0.48), 0.1),
        (0.5, _offsets(RSP=-0.50, RSR=-0.20, RE=0.48, RWR=0.65), 0.05),
        (0.5, _offsets(RSP=-0.50, RSR=-0.20, RE=0.48, RWR=-0.45), 0.05),
        (0.5, _offsets(RSP=-0.50, RSR=-0.20, RE=0.48, RWR=0.65), 0.2),
    ],
    "raise_hand_left": [(2.0, _offsets(LSP=-0.48, LSR=0.18, LE=0.32), 0.8)],
    "raise_hand_right": [(2.0, _offsets(RSP=-0.48, RSR=-0.18, RE=0.32), 0.8)],
    "salute_left": [(2.0, _offsets(LSP=-0.40, LSR=0.16, LE=0.55, LWR=0.20), 0.8)],
    "salute_right": [(2.0, _offsets(RSP=-0.40, RSR=-0.16, RE=0.55, RWR=-0.20), 0.8)],
    "open_arms": [(2.0, _offsets(LSR=0.38, RSR=-0.38, LE=0.18, RE=0.18), 0.8)],
    "nod": [(1.1, _offsets(HP=0.20), 0.1), (0.8, _offsets(HP=-0.12), 0.15), (0.8, _offsets(HP=0.18), 0.2)],
    "look": [(1.5, _offsets(HY=0.32), 0.6)],
    "look_right": [(1.5, _offsets(HY=-0.32), 0.6)],
    "shake_head": [(1.1, _offsets(HY=0.28), 0.08), (0.8, _offsets(HY=-0.28), 0.08), (0.8, _offsets(HY=0.22), 0.2)],
    "listen_left": [(1.6, _offsets(HY=0.30, HP=0.06), 0.9)],
    "listen_right": [(1.6, _offsets(HY=-0.30, HP=0.06), 0.9)],
    "present_left": [(2.0, _offsets(LSP=-0.28, LSR=0.18, LE=0.28, HY=0.12), 0.8)],
    "present_right": [(2.0, _offsets(RSP=-0.28, RSR=-0.18, RE=0.28, HY=-0.12), 0.8)],
    "hands_forward": [(2.0, _offsets(LSP=-0.30, RSP=-0.30, LE=0.22, RE=0.22), 0.7)],
    "ready_pose": [(1.2, _offsets(), 0.2)],
    "small_cheer": [(1.8, _offsets(LSP=-0.42, RSP=-0.42, LE=0.32, RE=0.32), 0.5)],
    "dual_arm_gesture": [(1.6, _offsets(LSP=0.40, RSP=-0.40), 0.4), (1.2, _offsets(LSP=0.40, RSP=-0.40, LWR=0.72, RWR=-0.72), 0.6)],
    "clap": [
        (1.4, _offsets(LSP=-0.24, RSP=-0.24, LSR=0.14, RSR=-0.14, LE=0.45, RE=0.45), 0.1),
        (0.32, _offsets(LSP=-0.24, RSP=-0.24, LSR=0.14, RSR=-0.14, LE=0.45, RE=0.45, LWR=0.50, RWR=-0.50), 0.04),
        (0.32, _offsets(LSP=-0.24, RSP=-0.24, LSR=0.14, RSR=-0.14, LE=0.45, RE=0.45, LWR=-0.28, RWR=0.28), 0.04),
        (0.32, _offsets(LSP=-0.24, RSP=-0.24, LSR=0.14, RSR=-0.14, LE=0.45, RE=0.45, LWR=0.50, RWR=-0.50), 0.2),
    ],
    "come_here": [
        (1.4, _offsets(RSP=-0.40, RSR=-0.14, RE=0.55), 0.08),
        (0.4, _offsets(RSP=-0.40, RSR=-0.14, RE=0.28), 0.04),
        (0.4, _offsets(RSP=-0.40, RSR=-0.14, RE=0.55), 0.04),
        (0.4, _offsets(RSP=-0.40, RSR=-0.14, RE=0.28), 0.2),
    ],
    "point_left": [(1.8, _offsets(LSP=-0.34, LSR=0.24, LE=0.12, HY=0.22), 0.8)],
    "point_right": [(1.8, _offsets(RSP=-0.34, RSR=-0.24, RE=0.12, HY=-0.22), 0.8)],
    "stretch": [(2.2, _offsets(LSP=-0.52, RSP=-0.52, LE=0.12, RE=0.12), 0.7)],
    "hug": [(1.5, _offsets(LSR=0.36, RSR=-0.36, LE=0.12, RE=0.12), 0.2), (1.3, _offsets(LSR=0.08, RSR=-0.08, LE=0.38, RE=0.38), 0.6)],
    "akimbo": [(1.8, _offsets(LSR=0.30, RSR=-0.30, LE=0.52, RE=0.52), 0.8)],
    "waist_left": [(1.5, _offsets(WY=0.35), 0.5)],
    "waist_right": [(1.5, _offsets(WY=-0.35), 0.5)],
}

LOCO = {
    "move_forward_slow": (0.05, 0.0, 0.0, 0.5),
    "move_forward_long": (0.05, 0.0, 0.0, 1.5),
    "move_backward_slow": (-0.05, 0.0, 0.0, 0.5),
    "move_backward_long": (-0.05, 0.0, 0.0, 1.5),
    "move_left_slow": (0.0, 0.05, 0.0, 0.6),
    "move_right_slow": (0.0, -0.05, 0.0, 0.6),
    "turn_left_10": (0.0, 0.0, 0.35, 0.5),
    "turn_right_10": (0.0, 0.0, -0.35, 0.5),
    "turn_left_20": (0.0, 0.0, 0.35, 1.0),
    "turn_right_20": (0.0, 0.0, -0.35, 1.0),
    "turn_left_45": (0.0, 0.0, 0.35, 2.25),
    "turn_right_45": (0.0, 0.0, -0.35, 2.25),
    "turn_left_90": (0.0, 0.0, 0.35, 4.5),
    "turn_right_90": (0.0, 0.0, -0.35, 4.5),
    "stop_move": (0.0, 0.0, 0.0, 0.0),
}


def _blend(x: float) -> float:
    return 10 * x**3 - 15 * x**4 + 6 * x**5


class DdsRobot:
    def __init__(self, interface: str = "en5") -> None:
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelPublisher, ChannelSubscriber
        from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
        from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_
        from unitree_sdk2py.idl.std_msgs.msg.dds_ import String_
        from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowCmd_, LowState_
        from unitree_sdk2py.r1.loco.r1_loco_client import LocoClient
        from unitree_sdk2py.utils.crc import CRC

        ChannelFactoryInitialize(0, interface)
        self._state = None
        self._audio_lines: list[str] = []
        self._cmd = unitree_hg_msg_dds__LowCmd_()
        self._crc = CRC()
        self._lowstate = ChannelSubscriber("rt/lowstate", LowState_)
        self._lowstate.Init(self._on_lowstate, 10)
        deadline = time.time() + 5
        while self._state is None and time.time() < deadline:
            time.sleep(0.05)
        if self._state is None:
            raise RuntimeError("rt/lowstate timed out on " + interface)
        self._arm = ChannelPublisher("rt/arm_sdk", LowCmd_)
        self._arm.Init()
        self._asr = ChannelSubscriber("rt/audio_msg", String_)
        self._asr.Init(self._on_audio, 10)
        self._tts = AudioClient()
        self._tts.SetTimeout(10.0)
        self._tts.Init()
        self._loco = LocoClient()
        self._loco.SetTimeout(2.0)
        self._loco.Init()

    def _on_lowstate(self, msg) -> None:
        self._state = msg

    def _on_audio(self, msg) -> None:
        raw = getattr(msg, "data", "")
        if not raw:
            return
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            self._audio_lines.append(raw)
            return
        if isinstance(payload, dict) and not payload.get("text"):
            return
        self._audio_lines.append(raw)

    def _pose(self) -> list[float]:
        return [float(self._state.motor_state[joint].q) for joint in JOINTS]

    def _check(self) -> None:
        for joint in JOINTS:
            if self._state.motor_state[joint].temperature[0] > 70:
                raise RuntimeError("temperature exceeded 70 C")
        roll, pitch = self._state.imu_state.rpy[0], self._state.imu_state.rpy[1]
        if abs(roll) > 0.35 or abs(pitch) > 0.35:
            raise RuntimeError("IMU envelope exceeded")

    def _publish(self, pose: list[float], weight: float) -> None:
        self._cmd.mode_pr = int(max(0.0, min(1.0, weight)) * 100)
        for index, joint in enumerate(JOINTS):
            cmd = self._cmd.motor_cmd[joint]
            cmd.q = pose[index]
            cmd.dq = 0.0
            cmd.tau = 0.0
            cmd.kp = KP[index]
            cmd.kd = KD[index]
        self._cmd.crc = self._crc.Crc(self._cmd)
        self._arm.Write(self._cmd)

    def _move_pose(self, start: list[float], end: list[float], seconds: float) -> None:
        t0 = time.time()
        while True:
            x = min(1.0, (time.time() - t0) / max(seconds, 0.01))
            s = _blend(x)
            pose = [a + (b - a) * s for a, b in zip(start, end)]
            self._publish(pose, 1.0)
            self._check()
            if x >= 1.0:
                return
            time.sleep(0.01)

    def _release(self) -> None:
        pose = self._pose()
        t0 = time.time()
        while True:
            weight = max(0.0, 1.0 - (time.time() - t0))
            self._publish(pose, weight)
            if weight <= 0:
                return
            time.sleep(0.01)

    def speak(self, text: str) -> None:
        code = self._tts.TtsMaker(text, 0)
        if code != 0:
            raise RuntimeError(f"TTS failed with code {code}")

    def listen(self, timeout_s: int = 30, minimum_confidence: float = 0.45) -> str:
        self._audio_lines = []
        last_count = 0
        last_packet = None
        selected = None
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if len(self._audio_lines) != last_count:
                last_count = len(self._audio_lines)
                last_packet = time.time()
                print(f"ASR packet: {self._audio_lines[-1]}", flush=True)
            try:
                selected = select_transcript("\n".join(self._audio_lines), minimum_confidence=minimum_confidence)
            except ValueError:
                selected = None
            if selected and selected.get("is_final") is True:
                return selected["text"]
            if selected and last_packet and time.time() - last_packet >= 2.5:
                return selected["text"]
            time.sleep(0.05)
        if selected:
            return selected["text"]
        sample = self._audio_lines[-3:] if self._audio_lines else []
        raise RuntimeError(
            "ASR timeout: enable microphone wake mode using the R1 app or remote. "
            f"packets={len(self._audio_lines)} sample={sample}"
        )

    def arm(self, action: Action | str) -> None:
        name = action if isinstance(action, str) else action.name
        motion = MOTIONS.get(name)
        if motion is None:
            raise RuntimeError(f"unknown arm action: {name}")
        initial = self._pose()
        previous = initial[:]
        try:
            self._check()
            self._publish(initial, 1.0)
            for duration, offsets, hold in motion:
                target = [initial[i] + offsets[i] for i in range(13)]
                self._move_pose(previous, target, duration)
                time.sleep(hold)
                previous = target
            self._move_pose(previous, initial, 2.0)
            self._release()
        except Exception:
            self._release()
            raise

    def move(self, action: Action | str) -> None:
        name = action if isinstance(action, str) else action.name
        command = LOCO.get(name)
        if command is None:
            raise RuntimeError(f"unknown loco action: {name}")
        vx, vy, omega, duration = command
        if duration <= 0:
            stop = self._loco.StopMove()
            if stop not in (0, None):
                raise RuntimeError(f"StopMove failed with code {stop}")
            return
        code = self._loco.SetVelocity(vx, vy, omega, duration)
        if code != 0:
            self._loco.StopMove()
            raise RuntimeError(f"SetVelocity failed with code {code}")
        time.sleep(duration)
        stop = self._loco.StopMove()
        if stop not in (0, None):
            raise RuntimeError(f"StopMove failed with code {stop}")

    def turn(self, action: Action) -> None:
        self.move(action)

    def stop(self) -> None:
        return None
