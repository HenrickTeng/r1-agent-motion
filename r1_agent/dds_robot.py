from __future__ import annotations

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
    "wrist_wave": [(2.0, _offsets(RWR=0.35), 1.0)],
    "wrist_wave_left": [(2.0, _offsets(LWR=-0.30), 0.7)],
    "wave_left": [
        (1.8, _offsets(LSP=-0.42, LSR=0.18, LE=0.45), 0.15),
        (0.55, _offsets(LSP=-0.42, LSR=0.18, LE=0.45, LWR=0.55), 0.05),
        (0.55, _offsets(LSP=-0.42, LSR=0.18, LE=0.45, LWR=-0.40), 0.05),
        (0.55, _offsets(LSP=-0.42, LSR=0.18, LE=0.45, LWR=0.55), 0.25),
    ],
    "wave_right": [
        (1.8, _offsets(RSP=-0.42, RSR=-0.18, RE=0.45), 0.15),
        (0.55, _offsets(RSP=-0.42, RSR=-0.18, RE=0.45, RWR=0.55), 0.05),
        (0.55, _offsets(RSP=-0.42, RSR=-0.18, RE=0.45, RWR=-0.40), 0.05),
        (0.55, _offsets(RSP=-0.42, RSR=-0.18, RE=0.45, RWR=0.55), 0.25),
    ],
    "raise_hand_left": [(2.5, _offsets(LSP=-0.20, LSR=0.12, LE=0.20), 1.0)],
    "raise_hand_right": [(2.5, _offsets(RSP=-0.20, RSR=-0.12, RE=0.20), 1.0)],
    "salute_left": [(2.5, _offsets(LSP=-0.18, LSR=0.10, LE=0.28), 1.0)],
    "salute_right": [(2.5, _offsets(RSP=-0.18, RSR=-0.10, RE=0.28), 1.0)],
    "open_arms": [(2.5, _offsets(LSR=0.14, RSR=-0.14), 1.0)],
    "nod": [(1.5, _offsets(HP=0.10), 0.2), (1.0, _offsets(HP=-0.06), 0.4)],
    "look": [(1.8, _offsets(HY=0.15), 0.5)],
    "shake_head": [(1.5, _offsets(HY=0.12), 0.2), (1.0, _offsets(HY=-0.12), 0.4)],
    "listen_left": [(1.8, _offsets(HY=0.15), 1.0)],
    "listen_right": [(1.8, _offsets(HY=-0.15), 1.0)],
    "present_left": [(2.2, _offsets(LSP=-0.12, LSR=0.10, LE=0.15), 1.0)],
    "present_right": [(2.2, _offsets(RSP=-0.12, RSR=-0.10, RE=0.15), 1.0)],
    "hands_forward": [(2.3, _offsets(LSP=-0.12, RSP=-0.12, LE=0.12, RE=0.12), 0.8)],
    "ready_pose": [(1.5, _offsets(), 0.3)],
    "small_cheer": [(2.5, _offsets(LSP=-0.16, RSP=-0.16, LE=0.20, RE=0.20), 0.7)],
    "dual_arm_gesture": [(2.0, _offsets(LSP=0.36, RSP=-0.36), 0.6), (1.5, _offsets(LSP=0.36, RSP=-0.36, LWR=0.72, RWR=-0.72), 0.8)],
}

LOCO = {
    "move_forward_slow": (0.05, 0.0, 0.0, 0.5),
    "move_backward_slow": (-0.05, 0.0, 0.0, 0.5),
    "move_left_slow": (0.0, 0.05, 0.0, 0.6),
    "move_right_slow": (0.0, -0.05, 0.0, 0.6),
    "turn_left_10": (0.0, 0.0, 0.35, 0.5),
    "turn_right_10": (0.0, 0.0, -0.35, 0.5),
    "turn_left_20": (0.0, 0.0, 0.35, 1.0),
    "turn_right_20": (0.0, 0.0, -0.35, 1.0),
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
        text = getattr(msg, "data", "")
        if text:
            self._audio_lines.append(text)

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
        count = 0
        last = None
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if len(self._audio_lines) != count:
                count = len(self._audio_lines)
                last = time.time()
            if last is not None and time.time() - last >= 1.5:
                break
            time.sleep(0.05)
        if not self._audio_lines:
            raise RuntimeError("ASR timeout: enable microphone wake mode using the R1 app or remote.")
        return select_transcript("\n".join(self._audio_lines), minimum_confidence=minimum_confidence)["text"]

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
