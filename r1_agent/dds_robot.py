from __future__ import annotations

import json
import math
import threading
import time

from r1_agent.asr import select_transcript
from r1_agent.arm_safety import DT_S, move_duration_s, slew_toward
from r1_agent.catalog import Action
from r1_agent.elbow_map import pose13_elbows_human_to_hw

JOINTS = (15, 16, 17, 18, 19, 22, 23, 24, 25, 26, 13, 29, 30)
KP = (50, 50, 40, 40, 30, 50, 50, 40, 40, 30, 50, 15, 15)
KD = (2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 1, 1)
LSP, LSR, LSY, LE, LWR = 0, 1, 2, 3, 4
RSP, RSR, RSY, RE, RWR = 5, 6, 7, 8, 9
WY, HP, HY = 10, 11, 12


AMPLITUDE = 1.8
SHOULDER_PITCH = 3.0

# 自然站直时的 13 关节绝对角度（度），即「准备姿态」零位，来自真机 read_ready_pose.py
READY_POSE_DEG = (
    13.381,   # LSP 左肩俯仰
    10.569,   # LSR 左肩横滚
    1.323,    # LSY 左肩偏航
    45.182,   # LE  左肘
    -0.25,    # LWR 左腕横滚
    13.585,   # RSP 右肩俯仰
    -10.227,  # RSR 右肩横滚
    -1.279,   # RSY 右肩偏航
    45.857,   # RE  右肘
    0.372,    # RWR 右腕横滚
    -0.343,   # WY  腰偏航
    0.132,    # HP  头俯仰
    0.345,    # HY  头偏航
)


def _deg(**joints: float) -> tuple[float, ...]:
    """把「系数」换算成「绝对角度（度）」：绝对角度 = ready_pose + 系数×振幅×180/π。

    未指定的关节保持 ready_pose 的绝对角度。返回 13 维元组，单位是度。
    """
    pose = list(READY_POSE_DEG)
    names = {"LSP": LSP, "LSR": LSR, "LSY": LSY, "LE": LE, "LWR": LWR, "RSP": RSP, "RSR": RSR, "RSY": RSY, "RE": RE, "RWR": RWR, "WY": WY, "HP": HP, "HY": HY}
    for name, value in joints.items():
        scale = SHOULDER_PITCH if name in ("LSP", "RSP") else AMPLITUDE
        offset_deg = value * scale * 180.0 / math.pi
        pose[names[name]] = READY_POSE_DEG[names[name]] + offset_deg
    return tuple(pose)


MOTIONS: dict[str, list[tuple[float, tuple[float, ...], float]]] = {
    "wrist_wave": [
        (1.2, _deg(RWR=0.55), 0.05),
        (0.8, _deg(RWR=-0.45), 0.08),
        (0.8, _deg(RWR=0.55), 0.2),
    ],
    "wrist_wave_left": [
        (1.2, _deg(LWR=-0.55), 0.05),
        (0.8, _deg(LWR=0.45), 0.08),
        (0.8, _deg(LWR=-0.55), 0.2),
    ],
    "wave_left": [
        (2.0, _deg(LSP=-0.50, LSR=0.20), 0.1),
        (1.0, _deg(LSP=-0.50, LSR=0.20, LWR=0.65), 0.08),
        (1.0, _deg(LSP=-0.50, LSR=0.20, LWR=-0.45), 0.08),
        (1.0, _deg(LSP=-0.50, LSR=0.20, LWR=0.65), 0.2),
    ],
    "wave_right": [
        (2.0, _deg(RSP=-0.50, RSR=-0.20), 0.1),
        (1.0, _deg(RSP=-0.50, RSR=-0.20, RWR=0.65), 0.08),
        (1.0, _deg(RSP=-0.50, RSR=-0.20, RWR=-0.45), 0.08),
        (1.0, _deg(RSP=-0.50, RSR=-0.20, RWR=0.65), 0.2),
    ],
    "raise_hand_left": [(2.0, _deg(LSP=-0.48, LSR=0.18, LE=0.32), 0.8)],
    "raise_hand_right": [(2.0, _deg(RSP=-0.48, RSR=-0.18, RE=0.32), 0.8)],
    "salute_left": [(2.0, _deg(LSP=-0.40, LSR=0.16, LE=0.55, LWR=0.20), 0.8)],
    "salute_right": [(2.0, _deg(RSP=-0.40, RSR=-0.16, RE=0.55, RWR=-0.20), 0.8)],
    "open_arms": [(2.0, _deg(LSP=-0.40, RSP=-0.40, LSR=0.38, RSR=-0.38, LE=0.18, RE=0.18), 0.8)],
    "nod": [(1.1, _deg(HP=0.20), 0.1), (0.8, _deg(HP=-0.12), 0.15), (0.8, _deg(HP=0.18), 0.2)],
    "look": [(1.5, _deg(HY=0.32), 0.6)],
    "look_right": [(1.5, _deg(HY=-0.32), 0.6)],
    "shake_head": [(1.1, _deg(HY=0.28), 0.08), (0.8, _deg(HY=-0.28), 0.08), (0.8, _deg(HY=0.22), 0.2)],
    "listen_left": [(1.6, _deg(HY=0.30, HP=0.06), 0.9)],
    "listen_right": [(1.6, _deg(HY=-0.30, HP=0.06), 0.9)],
    "present_left": [(2.0, _deg(LSP=-0.28, LSR=0.18, LE=0.28, HY=0.12), 0.8)],
    "present_right": [(2.0, _deg(RSP=-0.28, RSR=-0.18, RE=0.28, HY=-0.12), 0.8)],
    "hands_forward": [(2.0, _deg(LSP=-0.30, RSP=-0.30, LE=0.22, RE=0.22), 0.7)],
    "ready_pose": [(1.2, _deg(), 0.2)],
    "small_cheer": [(1.8, _deg(LSP=-0.42, RSP=-0.42, LE=0.32, RE=0.32), 0.5)],
    "cheer_both": [
        # 举起（比原来水平再往上很多），两手肩偏航差约 10°，前后交替晃
        (1.8, _deg(LSP=-0.78, RSP=-0.78, LSR=0.16, RSR=-0.16, LSY=0.10, RSY=-0.10, LE=0.08, RE=0.08), 0.06),
        (0.32, _deg(LSP=-0.78, RSP=-0.78, LSR=0.16, RSR=-0.16, LSY=-0.10, RSY=0.10, LE=0.08, RE=0.08, LWR=0.25, RWR=-0.25), 0.04),
        (0.32, _deg(LSP=-0.78, RSP=-0.78, LSR=0.16, RSR=-0.16, LSY=0.10, RSY=-0.10, LE=0.08, RE=0.08, LWR=-0.25, RWR=0.25), 0.04),
        (0.32, _deg(LSP=-0.78, RSP=-0.78, LSR=0.16, RSR=-0.16, LSY=-0.10, RSY=0.10, LE=0.08, RE=0.08, LWR=0.25, RWR=-0.25), 0.04),
        (0.32, _deg(LSP=-0.78, RSP=-0.78, LSR=0.16, RSR=-0.16, LSY=0.10, RSY=-0.10, LE=0.08, RE=0.08, LWR=-0.25, RWR=0.25), 0.18),
    ],
    "dual_arm_gesture": [(1.6, _deg(LSP=0.40, RSP=-0.40), 0.4), (1.2, _deg(LSP=0.40, RSP=-0.40, LWR=0.72, RWR=-0.72), 0.6)],
    "clap": [
        (1.4, _deg(LSP=-0.24, RSP=-0.24, LSR=0.14, RSR=-0.14, LE=0.45, RE=0.45), 0.1),
        (0.7, _deg(LSP=-0.24, RSP=-0.24, LSR=0.14, RSR=-0.14, LE=0.45, RE=0.45, LWR=0.50, RWR=-0.50), 0.06),
        (0.7, _deg(LSP=-0.24, RSP=-0.24, LSR=0.14, RSR=-0.14, LE=0.45, RE=0.45, LWR=-0.28, RWR=0.28), 0.06),
        (0.7, _deg(LSP=-0.24, RSP=-0.24, LSR=0.14, RSR=-0.14, LE=0.45, RE=0.45, LWR=0.50, RWR=-0.50), 0.2),
    ],
    "come_here": [
        (1.4, _deg(RSP=-0.40, RSR=-0.14, RE=0.55), 0.08),
        (0.8, _deg(RSP=-0.40, RSR=-0.14, RE=0.28), 0.06),
        (0.8, _deg(RSP=-0.40, RSR=-0.14, RE=0.55), 0.06),
        (0.8, _deg(RSP=-0.40, RSR=-0.14, RE=0.28), 0.2),
    ],
    "point_left": [(1.8, _deg(LSP=-0.34, LSR=0.24, LE=0.12, HY=0.22), 0.8)],
    "point_right": [(1.8, _deg(RSP=-0.34, RSR=-0.24, RE=0.12, HY=-0.22), 0.8)],
    "stretch": [(2.2, _deg(LSP=-0.52, RSP=-0.52, LE=0.12, RE=0.12), 0.7)],
    "hug": [(1.5, _deg(LSP=-0.50, RSP=-0.50, LSR=0.36, RSR=-0.36, LE=0.12, RE=0.12), 0.2), (1.3, _deg(LSP=-0.45, RSP=-0.45, LSR=0.08, RSR=-0.08, LE=0.38, RE=0.38), 0.6)],
    "akimbo": [(1.8, _deg(LSR=0.30, RSR=-0.30, LE=0.52, RE=0.52), 0.8)],
    "waist_left": [(1.5, _deg(WY=0.35), 0.5)],
    "waist_right": [(1.5, _deg(WY=-0.35), 0.5)],
}

LOCO = {
    "move_forward_slow": (0.5, 0.0, 0.0, 0.5),
    "move_forward_long": (0.5, 0.0, 0.0, 1.0),
    "move_backward_slow": (-0.5, 0.0, 0.0, 0.5),
    "move_backward_long": (-0.5, 0.0, 0.0, 1.0),
    "move_left_slow": (0.0, 0.5, 0.0, 1.0),
    "move_right_slow": (0.0, -0.5, 0.0, 1.0),
    "turn_left_10": (0.0, 0.0, 1.0, 0.2),
    "turn_right_10": (0.0, 0.0, -1.0, 0.2),
    "turn_left_20": (0.0, 0.0, 1.0, 0.35),
    "turn_right_20": (0.0, 0.0, -1.0, 0.35),
    "turn_left_45": (0.0, 0.0, 1.0, 0.79),
    "turn_right_45": (0.0, 0.0, -1.0, 0.79),
    "turn_left_90": (0.0, 0.0, 1.0, 1.57),
    "turn_right_90": (0.0, 0.0, -1.0, 1.57),
    "stop_move": (0.0, 0.0, 0.0, 0.0),
}


def _loco_issued(code: int | None) -> bool:
    return code in (0, 127, None)


# 固件可行走族：811 走跑；816 是 arm_sdk 接管后的 ArmSdkLoco，不是“没进走跑”。
WALK_FSMS = frozenset({811, 812, 813, 814, 815, 816, 830, 831})
FSM_NAMES = {
    0: "ZeroTorque",
    1: "Damping",
    4: "Lock",
    811: "Run",
    814: "Walk",
    816: "ArmSdkLoco",
    830: "Loco20Dof",
    831: "LocoArmSdk",
}


def _blend(x: float) -> float:
    return 10 * x**3 - 15 * x**4 + 6 * x**5


class DdsRobot:
    def __init__(self, interface: str = "auto") -> None:
        from r1_agent.dds_setup import prepare_cyclonedds

        prepare_cyclonedds()
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelPublisher, ChannelSubscriber
        from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_
        from unitree_sdk2py.idl.std_msgs.msg.dds_ import String_
        from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowCmd_, LowState_
        from unitree_sdk2py.utils.crc import CRC

        from r1_agent.interface import resolve_interface

        self._interface = resolve_interface(interface)
        ChannelFactoryInitialize(0, self._interface)
        self._state = None
        self._audio_lines: list[str] = []
        self._cmd = unitree_hg_msg_dds__LowCmd_()
        self._crc = CRC()
        self._tts = None
        self._loco = None
        self._init_lock = threading.Lock()
        t0 = time.time()
        print(f"DDS 网卡 {self._interface}，等待 rt/lowstate…", flush=True)
        self._lowstate = ChannelSubscriber("rt/lowstate", LowState_)
        self._lowstate.Init(self._on_lowstate, 10)
        deadline = time.time() + 5
        while self._state is None and time.time() < deadline:
            time.sleep(0.05)
        if self._state is None:
            raise RuntimeError("rt/lowstate timed out on " + self._interface)
        print(f"rt/lowstate 已到（{time.time() - t0:.1f}s）", flush=True)
        self._arm = ChannelPublisher("rt/arm_sdk", LowCmd_)
        self._arm.Init()
        self._asr = ChannelSubscriber("rt/audio_msg", String_)
        self._asr.Init(self._on_audio, 10)
        self._q_cmd = self._pose()
        self._estop = False
        self._loco_lock = threading.Lock()
        self._fsm_cache: tuple[int | None, float] = (None, 0.0)
        self._moving = False

    def _on_lowstate(self, msg) -> None:
        self._state = msg

    def _ensure_tts(self):
        with self._init_lock:
            if self._tts is not None:
                return
            from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient

            t0 = time.time()
            print("正在初始化语音客户端…", flush=True)
            tts = AudioClient()
            tts.SetTimeout(5.0)
            tts.Init()
            self._tts = tts
            print(f"语音客户端就绪 {time.time() - t0:.1f}s", flush=True)

    def _ensure_loco(self):
        with self._init_lock:
            if self._loco is not None:
                return
            from unitree_sdk2py.r1.loco.r1_loco_client import LocoClient

            t0 = time.time()
            print("正在初始化行走客户端…", flush=True)
            loco = LocoClient()
            loco.SetTimeout(2.0)
            loco.Init()
            self._loco = loco
            print(f"行走客户端就绪 {time.time() - t0:.1f}s", flush=True)

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
        if abs(roll) > 0.5 or abs(pitch) > 0.5:
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
        if self._estop:
            raise RuntimeError("soft estop: motion blocked")
        duration = move_duration_s(start, end, seconds)
        t0 = time.time()
        while True:
            if self._estop:
                raise RuntimeError("soft estop: motion blocked")
            x = min(1.0, (time.time() - t0) / max(duration, 0.01))
            s = _blend(x)
            pose = [a + (b - a) * s for a, b in zip(start, end)]
            self._q_cmd = pose
            self._publish(pose, 1.0)
            self._check()
            if x >= 1.0:
                return
            time.sleep(DT_S)

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
        self._ensure_tts()
        code = self._tts.TtsMaker(text, 0)
        if code != 0:
            raise RuntimeError(f"TTS failed with code {code}")

    def listen(self, timeout_s: int = 45, minimum_confidence: float = 0.45, silence_s: float = 3.0) -> str:
        self._audio_lines = []
        last_count = 0
        last_packet = None
        selected = None
        started = time.time()
        while True:
            now = time.time()
            if selected is None and now - started >= timeout_s:
                sample = self._audio_lines[-3:] if self._audio_lines else []
                raise RuntimeError(
                    "ASR timeout: enable microphone wake mode using the R1 app or remote. "
                    f"packets={len(self._audio_lines)} sample={sample}"
                )
            if len(self._audio_lines) != last_count:
                last_count = len(self._audio_lines)
                last_packet = now
                print(f"ASR packet: {self._audio_lines[-1]}", flush=True)
            try:
                selected = select_transcript("\n".join(self._audio_lines), minimum_confidence=minimum_confidence)
            except ValueError:
                selected = None
            if selected and last_packet and now - last_packet >= silence_s:
                return selected["text"]
            time.sleep(0.05)

    def arm(self, action: Action | str) -> None:
        name = action if isinstance(action, str) else action.name
        motion = MOTIONS.get(name)
        if motion is None:
            raise RuntimeError(f"unknown arm action: {name}")
        ready = [math.radians(deg) for deg in READY_POSE_DEG]
        current = self._pose()
        try:
            self._check()
            self._publish(current, 1.0)
            # 执行前先回 ready_pose（安全零位），保证绝对角度有稳定参考
            self._move_pose(current, ready, 2.0)
            previous = ready[:]
            for duration, target_deg, hold in motion:
                target = [math.radians(deg) for deg in target_deg]
                self._move_pose(previous, target, duration)
                time.sleep(hold)
                previous = target
            # 执行后回 ready_pose（二次保证安全）
            self._move_pose(previous, ready, 2.0)
            self._release()
        except Exception:
            if self._estop:
                try:
                    self._publish(self._q_cmd, 1.0)
                except Exception:
                    pass
            else:
                self._release()
            raise

    def _fsm_id(self, *, block: bool = True) -> int | None:
        now = time.time()
        cached, stamp = self._fsm_cache
        ttl = 1.5 if block else 60.0
        if cached is not None and now - stamp < ttl:
            return cached
        if not block:
            return cached
        self._ensure_loco()
        from unitree_sdk2py.r1.loco.r1_loco_api import ROBOT_API_ID_LOCO_GET_FSM_ID
        code, data = self._loco._Call(ROBOT_API_ID_LOCO_GET_FSM_ID, "{}")
        if code != 0 or data in (None, ""):
            return cached
        try:
            payload = json.loads(data) if isinstance(data, str) else data
            fsm = int(payload["data"])
        except (json.JSONDecodeError, TypeError, KeyError, ValueError):
            return cached
        self._fsm_cache = (fsm, now)
        return fsm

    def _need_walk(self, fsm: int | None) -> None:
        if fsm is None or fsm in WALK_FSMS:
            return
        name = FSM_NAMES.get(fsm, "未知")
        raise RuntimeError(
            f"loco fsm_id={fsm}（{name}），不能 SetVelocity。"
            "先站稳，遥控器 R2+A 进走跑。不要软件 Start()/Damp。"
        )

    def require_walk_run(self) -> int:
        """走跑模式 fsm 811。只查询，不 SetFsmId。"""
        fsm = self._fsm_id()
        if fsm != 811 and fsm not in WALK_FSMS:
            raise RuntimeError(
                f"当前 fsm_id={fsm}，需要走跑（811 或 ArmSdkLoco 816）。保持站稳，不要进调试，不要 Damp。"
            )
        return fsm if fsm is not None else -1

    def move(self, action: Action | str) -> None:
        name = action if isinstance(action, str) else action.name
        command = LOCO.get(name)
        if command is None:
            raise RuntimeError(f"unknown loco action: {name}")
        vx, vy, omega, duration = command
        if duration <= 0:
            with self._loco_lock:
                stop = self._loco.StopMove()
                self._moving = False
            if not _loco_issued(stop):
                raise RuntimeError(f"StopMove failed with code {stop}")
            return
        fsm = self._fsm_id(block=False)
        self._need_walk(fsm)
        self.drive(vx, vy, omega, duration)
        if duration > 0:
            time.sleep(duration)

    def turn(self, action: Action) -> None:
        self.move(action)

    def drive(self, vx: float, vy: float, omega: float, duration: float = 0.25) -> None:
        """键盘/手势遥控：短时速度。松开必须 StopMove；本函数不 sleep。"""
        if self._estop:
            raise RuntimeError("soft estop: motion blocked")
        vx = max(-0.5, min(0.5, float(vx)))
        vy = max(-0.5, min(0.5, float(vy)))
        omega = max(-1.0, min(1.0, float(omega)))
        if abs(vx) + abs(vy) + abs(omega) < 1e-3:
            if self._loco is None:
                return
            with self._loco_lock:
                self._stop_locked()
            return
        self._ensure_loco()
        fsm = self._fsm_id(block=False)
        self._need_walk(fsm)
        with self._loco_lock:
            code = self._loco.SetVelocity(vx, vy, omega, max(0.5, float(duration)))
            if not _loco_issued(code):
                self._loco.StopMove()
                self._moving = False
                raise RuntimeError(f"SetVelocity failed with code {code} fsm_id={fsm}")
            self._moving = True

    def _stop_locked(self) -> None:
        if self._loco is None:
            self._moving = False
            return
        try:
            self._loco.StopMove()
        except Exception:
            pass
        self._moving = False

    def track_arm(self, arm_rad: dict[str, float], dt: float) -> None:
        """实时跟臂：10 个上肢关节，腰/头保持待机。已急停则只维持当前指令。"""
        ready = [math.radians(deg) for deg in READY_POSE_DEG]
        names = (
            "left_shoulder_pitch",
            "left_shoulder_roll",
            "left_shoulder_yaw",
            "left_elbow",
            "left_wrist_roll",
            "right_shoulder_pitch",
            "right_shoulder_roll",
            "right_shoulder_yaw",
            "right_elbow",
            "right_wrist_roll",
        )
        target = list(self._q_cmd if self._q_cmd else ready)
        if len(target) < 13:
            target = ready[:]
        if arm_rad:
            for index, name in enumerate(names):
                if name in arm_rad:
                    target[index] = float(arm_rad[name])
            target = pose13_elbows_human_to_hw(target)
        target[10] = ready[10]
        target[11] = ready[11]
        target[12] = ready[12]
        if not self._estop:
            self._q_cmd = slew_toward(self._q_cmd if len(self._q_cmd) == 13 else ready, target, dt)
        self._publish(self._q_cmd, 1.0)
        self._check()

    def goto_ready(self, seconds: float = 3.0) -> None:
        current = self._pose()
        ready = [math.radians(deg) for deg in READY_POSE_DEG]
        self._publish(current, 1.0)
        self._q_cmd = current
        self._move_pose(current, ready, seconds)

    def soft_estop(self) -> None:
        """软急停：停步 + 锁住当前上肢指令。不进 Damp，以免摔倒。"""
        self._estop = True
        with self._loco_lock:
            self._stop_locked()
        self._q_cmd = self._pose()
        self._publish(self._q_cmd, 1.0)

    def clear_estop(self) -> None:
        self._estop = False
        self._q_cmd = self._pose()

    def stop(self) -> None:
        if not self._loco_lock.acquire(timeout=0.2):
            return
        try:
            self._stop_locked()
            if self._state is not None:
                self._q_cmd = self._pose()
                self._publish(self._q_cmd, 1.0)
        finally:
            self._loco_lock.release()
