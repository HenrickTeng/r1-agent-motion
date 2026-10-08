from __future__ import annotations

import threading
import time
from pathlib import Path

from r1_agent.catalog import Catalog, load_catalog
from r1_agent.executor import Executor
from r1_agent.planner import (
    DeepSeekPlanner,
    RulePlanner,
    load_deepseek_key,
    load_deepseek_model,
    load_deepseek_url,
)
from r1_studio.camera import FrameSource
from r1_studio.body import BodyPilot
from r1_studio.gestures import GestureCommand, GesturePilot, classify_hand
from r1_studio.operator import OperatorLock
from r1_studio.presets import PRESETS
from r1_studio.programs import (
    ProgramError,
    apply_custom_groups,
    expand_steps,
    load_groups_file,
    load_program,
    save_groups_file,
    validate_group_name,
)
from r1_studio.teleop import clamp_twist, keys_to_twist, twist_duration
from r1_studio.proximity import GREET_CONTEXT, GreetPilot, drop_locomotion
from r1_studio.vision import (
    Detection,
    ask_campus,
    is_vision_intent,
    load_campus_text,
)

WALK_MODES = frozenset({"teleop", "gesture", "vision", "blocks", "agent", "imitate", "greet"})
STUDIO_MODES = WALK_MODES | {"idle", "wrestle"}
WRESTLE_LEAVE_HINT = (
    "扳手腕需要遥控器把 R1 切到调试模式。调试结束后，教师操作台用的走跑控制会失效，"
    "必须先给 R1 关机再开机，确认站稳走跑后，再在本页点「已重新开机」。网页不能替你开机。"
)


class StudioSession:
    def __init__(
        self,
        *,
        backend,
        camera: FrameSource,
        hardware: bool,
        listen_robot=None,
        groups_path: Path,
        scene: str = "",
        mirrored_camera: bool = True,
        face_to_face: bool = True,
        preview_window: bool = False,
        interface: str = "auto",
        camera_source: str = "laptop",
        laptop_index: int = 0,
    ) -> None:
        self.backend = backend
        self.camera = camera
        self.hardware = hardware
        self.listen_robot = listen_robot
        self.groups_path = groups_path
        self.base_catalog = load_catalog()
        if scene:
            from r1_agent.catalog import load_scene_pack, merge_scene

            self.base_catalog = merge_scene(self.base_catalog, load_scene_pack(scene))
        self.custom_groups = load_groups_file(groups_path)
        self.mode = "idle"
        self.busy = False
        self.last_error = ""
        self.last_reply = "教师控制台已就绪。遥控器急停请一直握在手里。"
        self.last_vision: dict = {}
        self.llm_key = load_deepseek_key()
        self.llm_url = load_deepseek_url()
        self.llm_model = load_deepseek_model()
        self.campus_base = load_campus_text("context.txt")
        self.campus_library = load_campus_text("library.txt")
        self.campus_extra = ""
        self.library_on = False
        self.vision_turns: list[dict[str, str]] = []
        self.gesture_label = "手势未开启"
        self.gesture_detail = {
            "poses": [],
            "kind": "idle",
            "label": "手势未开启",
            "vx": 0.0,
            "vy": 0.0,
            "omega": 0.0,
            "operator": "off",
            "operator_label": "",
            "strategy": "hands",
            "issued": False,
            "skip": "",
        }
        self._last_gesture_drive = 0.0
        self._lock = threading.Lock()
        self._pilot = GesturePilot(mirrored=mirrored_camera, face_to_face=face_to_face)
        self._body = BodyPilot()
        self._hands = None
        self._pose = None
        self._detector = None
        self._operator = OperatorLock(enabled=False)
        self._last_persons: list[tuple[float, float, float, float]] = []
        self._person_tick = 0
        self._operator_was_locked = False
        self._stop_live = threading.Event()
        self._live_thread: threading.Thread | None = None
        self.preview_window = preview_window
        self.mirrored_camera = mirrored_camera
        self._interface = interface
        self.camera_source = "synthetic" if camera.label.startswith("无摄像头") else camera_source
        self.laptop_index = laptop_index
        if self.camera_source == "synthetic":
            self.last_reply = "还没打开摄像头。在画面下方点「笔记本摄像头」或「R1 机载摄像头」。"
        self._twist_lock = threading.Lock()
        self._last_twist_t = 0.0
        self._want_move = False
        self._deadman_stop = threading.Event()
        self._deadman = threading.Thread(target=self._deadman_loop, daemon=True)
        self._deadman.start()
        self._gesture_busy = False
        self.r1_needs_reboot = False
        self.imitate_label = "动作模仿未开启"
        self.greet_label = "近距迎宾未开启"
        self.greet_detail: dict = {
            "distance_m": None,
            "zone": "unknown",
            "source": "",
            "pose": "none",
            "note": "",
        }
        self._greet = GreetPilot()
        self._greet_busy = False
        self._dialog_planner: DeepSeekPlanner | None = None
        self._dialog_key = ""
        self.camera.start()

    def campus_context(self) -> str:
        parts = [self.campus_base]
        if self.library_on:
            parts.append(self.campus_library)
        if self.campus_extra.strip():
            parts.append(self.campus_extra.strip())
        return "\n\n".join(part for part in parts if part)

    def configure_campus(
        self,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        model: str | None = None,
        extra: str | None = None,
        library_on: bool | None = None,
    ) -> dict:
        if api_key is not None and api_key.strip():
            self.llm_key = api_key.strip()
        if api_url is not None and api_url.strip():
            from r1_agent.planner import normalize_chat_url

            self.llm_url = normalize_chat_url(api_url)
        if model is not None and model.strip():
            self.llm_model = model.strip()
        if extra is not None:
            self.campus_extra = extra
        if library_on is not None:
            self.library_on = bool(library_on)
        self.last_reply = "已保存校园识别设置。" + (
            "已加载图书馆平面。" if self.library_on else "当前没有图书馆内部平面，问路时只给类型和方向。"
        )
        return self.state()

    @property
    def catalog(self) -> Catalog:
        return apply_custom_groups(self.base_catalog, self.custom_groups)

    def state(self) -> dict:
        return {
            "mode": self.mode,
            "hardware": self.hardware,
            "robot_ready": True if not hasattr(self.backend, "ready") else bool(self.backend.ready),
            "busy": self.busy,
            "camera": self.camera.label,
            "camera_source": self.camera_source,
            "reply": self.last_reply,
            "error": self.last_error,
            "gesture": self.gesture_label,
            "gesture_detail": self.gesture_detail,
            "vision": self.last_vision,
            "campus": {
                "has_key": bool(self.llm_key),
                "url": self.llm_url,
                "model": self.llm_model,
                "library_on": self.library_on,
                "context": self.campus_context(),
                "turns": list(self.vision_turns[-12:]),
                "dialog": list(self._dialog_planner._turns[-12:]) if self._dialog_planner else [],
            },
            "groups": self.custom_groups,
            "presets": PRESETS,
            "r1_needs_reboot": self.r1_needs_reboot,
            "imitate": self.imitate_label,
            "greet": self.greet_label,
            "greet_detail": dict(self.greet_detail),
        }

    def debug_stereo(self) -> dict:
        from r1_studio.depth import inspect_stereo

        frame, _jpeg = self.camera.snapshot()
        info, preview = inspect_stereo(frame)
        info["camera"] = self.camera.label
        info["camera_source"] = self.camera_source
        if preview is not None:
            try:
                import cv2

                cv2.imwrite("/tmp/r1_sgbm_local.jpg", preview)
                info["preview"] = "/tmp/r1_sgbm_local.jpg"
            except Exception:
                pass
        return info

    def catalog_payload(self) -> dict:
        catalog = self.catalog
        return {
            "actions": [
                {
                    "name": action.name,
                    "title": action.title,
                    "kind": action.kind,
                    "aliases": list(action.aliases),
                }
                for action in catalog.actions.values()
            ],
            "compositions": self.base_catalog.compositions,
            "speech": catalog.speech,
        }

    def set_mode(self, mode: str) -> None:
        if mode not in STUDIO_MODES:
            raise ProgramError("未知模式")
        if mode in WALK_MODES and self.r1_needs_reboot:
            raise ProgramError(WRESTLE_LEAVE_HINT)
        previous = self.mode
        self._shutdown_activity()
        self.mode = mode
        self.busy = False
        self.last_error = ""
        if mode == "wrestle":
            self.r1_needs_reboot = True
            self.last_reply = WRESTLE_LEAVE_HINT
            return
        if mode == "gesture":
            self._last_gesture_drive = 0.0
            self._operator.reset()
            self._body.reset()
            self._start_live()
            self.gesture_label = (
                "请侧平举或双手上举，用全身姿势锁定"
                if self.camera_source == "r1"
                else "手势操作已开启"
            )
            return
        if mode == "imitate":
            self._start_live()
            self.imitate_label = "动作模仿已开启。人的右手 → 机器人左臂。"
            self.last_reply = self.imitate_label
            if self.hardware:
                threading.Thread(target=self._imitate_prepare, daemon=True).start()
            return
        if mode == "teleop":
            self.last_reply = "键盘遥控已开启。请先点一下旁边的 QWEASD 格子，浏览器才会接收按键。"
            return
        if mode == "agent":
            self.last_reply = "课堂语音问答已开启。可以打字或听一轮，和单独跑 r1-agent 一样。"
            return
        if mode == "greet":
            self._greet.reset()
            self._start_live()
            self.greet_label = "近距迎宾已开启。0.5–1.8 米挥手；半米内提醒退后；0.3 米内停手。"
            self.last_reply = self.greet_label + " 语音和打字会接上刚才的迎宾上下文，且不会走路。"
            return
        if mode == "idle":
            self.gesture_label = "手势未开启"
            self.imitate_label = "动作模仿未开启"
            self.greet_label = "近距迎宾未开启"

    def _shutdown_activity(self) -> None:
        """切换功能时把上一套后台整段停掉，求稳，卡顿可以接受。"""
        self._stop_live_loop()
        if self._live_thread is not None and not self._live_thread.is_alive():
            self._live_thread = None
        with self._twist_lock:
            self._want_move = False
        self.busy = False
        try:
            self.backend.stop()
        except Exception:
            pass

    def _stop_backend_quiet(self) -> None:
        try:
            self.backend.stop()
        except Exception:
            pass

    def clear_wrestle_reboot(self) -> dict:
        self.r1_needs_reboot = False
        self.last_reply = "已记录：R1 重新开机并回到走跑。可以再点「开始」。"
        self.last_error = ""
        return self.state()

    def _ensure_walk_ok(self) -> None:
        if self.r1_needs_reboot:
            raise ProgramError(WRESTLE_LEAVE_HINT)

    def _imitate_prepare(self) -> None:
        try:
            robot = getattr(self.backend, "robot", None) or self.listen_robot
            if robot is None:
                self.backend.goto_ready(1.0)
                return
            if hasattr(robot, "require_walk_run"):
                robot.require_walk_run()
            self.backend.goto_ready(2.5)
            self.last_reply = "已回课堂准备姿态，开始跟臂。"
        except Exception as error:
            self.last_error = str(error)
            self.imitate_label = f"跟臂准备失败：{error}"

    def switch_camera(self, source: str, camera: int = 0) -> dict:
        source = (source or "").strip().lower()
        if source not in ("laptop", "r1"):
            raise ProgramError("画面源请选笔记本摄像头或 R1 机载摄像头")
        if self.mode != "idle":
            self.set_mode("idle")
        from r1_studio.camera import open_camera

        index = int(camera if camera else self.laptop_index)
        new = open_camera(
            camera=None if source == "r1" else index,
            r1_camera=source == "r1",
            interface=self._interface,
            synthetic=False,
        )
        new.start()
        old = self.camera
        self.camera = new
        self.camera_source = source
        if source == "laptop":
            self.laptop_index = index
        self.mirrored_camera = source == "laptop"
        self._pilot.mirrored = self.mirrored_camera
        self._operator.enabled = False
        self._operator.reset()
        self._body.reset()
        self._last_persons = []
        self._hands = None
        self._pose = None
        try:
            old.close()
        except Exception:
            pass
        self.last_reply = (
            "已切换到笔记本摄像头（手部关键点）"
            if source == "laptop"
            else "已切换到 R1 机载摄像头。超广角用手部不可靠，改为跟臂同款全身 Pose：先侧平举锁定。"
        )
        self.last_error = ""
        return self.state()

    def teleop_keys(self, keys: list[str], *, slow: bool = False) -> dict:
        if self.r1_needs_reboot:
            return {"ok": False, "error": WRESTLE_LEAVE_HINT, "vx": 0.0, "vy": 0.0, "omega": 0.0, "duration": 0.0}
        if self.mode != "teleop":
            return {"ok": False, "error": "请先点「开始键盘遥控」", "vx": 0.0, "vy": 0.0, "omega": 0.0, "duration": 0.0}
        self.busy = False
        vx, vy, omega = keys_to_twist(keys, slow=slow)
        return self.drive(vx, vy, omega)

    def drive(self, vx: float, vy: float, omega: float) -> dict:
        if self.r1_needs_reboot:
            return {"ok": False, "error": WRESTLE_LEAVE_HINT, "vx": vx, "vy": vy, "omega": omega, "duration": 0.0}
        vx, vy, omega = clamp_twist(vx, vy, omega)
        moving = abs(vx) + abs(vy) + abs(omega) >= 1e-3
        if moving:
            with self._twist_lock:
                self._want_move = True
                self._last_twist_t = time.time()
        try:
            duration = twist_duration(vx, vy, omega)
            self.backend.drive(vx, vy, omega, duration or 0.5)
            if not moving:
                with self._twist_lock:
                    self._want_move = False
            self.last_error = ""
            print(
                f"TELEOP SetVelocity vx={vx:.2f} vy={vy:.2f} om={omega:.2f} dur={duration:.2f}",
                flush=True,
            )
            return {"ok": True, "vx": vx, "vy": vy, "omega": omega, "duration": duration}
        except Exception as error:
            try:
                self.backend.drive(0.0, 0.0, 0.0, 1.0)
            except Exception:
                pass
            with self._twist_lock:
                self._want_move = False
            self.last_error = str(error)
            return {"ok": False, "error": str(error)}

    def _deadman_loop(self) -> None:
        while not self._deadman_stop.wait(0.2):
            with self._twist_lock:
                stale = self._want_move and (time.time() - self._last_twist_t > 1.4)
            if not stale:
                continue
            try:
                self.backend.drive(0.0, 0.0, 0.0, 1.0)
            except Exception:
                pass
            with self._twist_lock:
                self._want_move = False
            self.last_error = "遥控超时已停步。松开按键应马上停；网页关掉也会停。"

    def estop(self) -> None:
        if self.mode != "idle":
            self.set_mode("idle")
        self.backend.soft_estop()
        with self._twist_lock:
            self._want_move = False
        self.last_reply = "软急停：已停步并锁住当前上肢。按恢复后再操作。"
        self.busy = False

    def clear_estop(self) -> None:
        self.backend.clear_estop()
        self.last_reply = "急停已解除。"

    def run_names(self, names: list[str], *, reply: str = "") -> dict:
        if self.r1_needs_reboot:
            return {"ok": False, "error": WRESTLE_LEAVE_HINT}
        catalog = self.catalog
        try:
            actions = expand_steps(names, catalog)
        except ProgramError as error:
            return {"ok": False, "error": str(error)}
        return self._execute(actions, reply or "执行动作组")

    def run_preset(self, preset_id: str) -> dict:
        for item in PRESETS:
            if item["id"] == preset_id:
                return self.run_names(item["steps"], reply=item["title"])
        return {"ok": False, "error": "没有这个预设"}

    def run_program(self, payload: dict) -> dict:
        if self.r1_needs_reboot:
            return {"ok": False, "error": WRESTLE_LEAVE_HINT}
        try:
            name, actions = load_program(payload, self.catalog)
        except ProgramError as error:
            return {"ok": False, "error": str(error)}
        return self._execute(actions, f"运行程序「{name}」")

    def validate_program(self, payload: dict) -> dict:
        try:
            name, actions = load_program(payload, self.catalog)
        except ProgramError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "name": name, "titles": [action.title for action in actions]}

    def inspect_program(self, payload: dict) -> dict:
        from r1_studio.programs import inspect_blocks

        try:
            index = payload.get("index")
            if index is not None:
                index = int(index)
            result = inspect_blocks(payload.get("blocks") or [], self.catalog, index=index)
            result["name"] = str(payload.get("name") or "未命名程序").strip()[:40]
            return result
        except ProgramError as error:
            return {"ok": False, "error": str(error)}

    def save_group(self, name: str, steps: list[str]) -> dict:
        catalog = self.catalog
        try:
            name = validate_group_name(name, catalog)
            if name in self.base_catalog.compositions and name not in self.custom_groups:
                raise ProgramError("不要覆盖系统动作组，请换一个自己的名字")
            if not steps:
                raise ProgramError("动作组至少要有一个原子动作")
            expand_steps(steps, catalog)
        except ProgramError as error:
            return {"ok": False, "error": str(error)}
        self.custom_groups[name] = list(steps)
        save_groups_file(self.groups_path, self.custom_groups)
        return {"ok": True, "groups": self.custom_groups}

    def delete_group(self, name: str) -> dict:
        self.custom_groups.pop(name, None)
        save_groups_file(self.groups_path, self.custom_groups)
        return {"ok": True, "groups": self.custom_groups}

    def _planner_context(self) -> str:
        if self.mode != "greet":
            return ""
        dist = self._greet.meters
        dist_text = "未知" if dist is None else f"{dist:.2f} 米"
        return GREET_CONTEXT + f"\n刚才视觉测距约 {dist_text}，安全区 {self._greet.zone}。"

    def _ensure_dialog_planner(self) -> DeepSeekPlanner | None:
        key = f"{self.llm_key}|{self.llm_url}|{self.llm_model}"
        use = bool(self.llm_key or load_deepseek_key())
        if not use:
            return self._dialog_planner
        if self._dialog_planner is None or self._dialog_key != key:
            self._dialog_planner = DeepSeekPlanner(
                self.catalog,
                context=self._planner_context(),
                api_url=self.llm_url,
                model=self.llm_model,
                api_key=self.llm_key,
            )
            self._dialog_key = key
        else:
            self._dialog_planner.catalog = self.catalog
            self._dialog_planner.context = self._planner_context()
        return self._dialog_planner

    def _remember_dialog(self, text: str, reply: str, names: list[str]) -> None:
        self._ensure_dialog_planner()
        if self._dialog_planner is None:
            return
        self._dialog_planner._remember(text, reply, names)

    def handle_text(self, text: str, *, speak_reply: bool | None = None) -> dict:
        text = text.strip()
        if not text:
            return {"ok": False, "error": "空文本"}
        if self.r1_needs_reboot:
            return {"ok": False, "error": WRESTLE_LEAVE_HINT}
        if self.mode == "vision" or is_vision_intent(text):
            return self.capture_vision(speak=True, question=text)
        planner = self._ensure_dialog_planner() or RulePlanner(self.catalog)
        try:
            reply, actions = planner.plan(text)
        except Exception as error:
            reply, actions = RulePlanner(self.catalog).plan(text)
            self.last_error = str(error)
        if self.mode == "greet":
            actions = drop_locomotion(actions)
            if not self._greet.allows_arm():
                actions = [item for item in actions if item.kind == "speech"]
                safety = self._greet.safety_reply()
                if safety:
                    reply = safety
        speak = self.hardware if speak_reply is None else speak_reply
        result = self._execute(actions, reply, speak=speak)
        result["heard"] = text
        return result

    def listen_once(self) -> dict:
        if self.r1_needs_reboot or self.mode == "wrestle":
            return {"ok": False, "error": WRESTLE_LEAVE_HINT}
        if self.listen_robot is None:
            return {"ok": False, "error": "仿真模式没有机器人麦克风，请在输入框里打字"}
        try:
            text = self.listen_robot.listen()
        except Exception as error:
            return {"ok": False, "error": str(error)}
        return self.handle_text(text, speak_reply=True)

    def capture_vision(self, *, speak: bool = True, question: str = "") -> dict:
        frame = self._prepared_frame()
        items: list[Detection] = []
        if frame is not None:
            items = self._detect(frame)
        from r1_studio.camera import _encode

        jpeg = _encode(frame) if frame is not None else b""
        asked = question.strip()
        reply = ask_campus(
            question=asked,
            detections=items,
            jpeg=jpeg,
            campus_context=self.campus_context(),
            history=self.vision_turns,
            api_key=self.llm_key,
            api_url=self.llm_url,
            model=self.llm_model,
        )
        if asked:
            self.vision_turns.append({"role": "user", "content": asked})
            self.vision_turns.append({"role": "assistant", "content": reply})
            self.vision_turns = self.vision_turns[-16:]
        self.last_vision = {
            "reply": reply,
            "question": asked,
            "items": [
                {
                    "label": item.label,
                    "title": item.title_zh,
                    "category": item.category,
                    "score": item.score,
                    "box": list(item.box),
                }
                for item in items
            ],
        }
        self.last_reply = reply
        if speak:
            try:
                self.backend.speak(reply)
            except Exception as error:
                self.last_error = str(error)
        return {"ok": True, **self.last_vision}

    def _detect(self, frame) -> list[Detection]:
        try:
            if self._detector is None:
                from r1_studio.vision import MediaPipeObjectDetector

                self._detector = MediaPipeObjectDetector()
            return self._detector.detect_bgr(frame)
        except Exception as error:
            self.last_error = f"检测器未就绪：{error}"
            return []

    def _prepared_frame(self):
        frame, _jpeg = self.camera.snapshot()
        return frame

    def _execute(self, actions, reply: str, *, speak: bool = False) -> dict:
        with self._lock:
            if self.busy:
                return {"ok": False, "error": "上一条动作还在执行"}
            self.busy = True
        with self._twist_lock:
            self._want_move = False
        self.last_reply = reply
        titles = [action.title for action in actions]
        try:
            if speak and reply:
                try:
                    self.backend.speak(reply)
                except Exception:
                    pass
            if actions:
                Executor(self.backend).execute(actions)
            self.last_error = ""
            return {"ok": True, "reply": reply, "actions": titles}
        except Exception as error:
            self.last_error = str(error)
            try:
                self.backend.stop()
            except Exception:
                pass
            return {"ok": False, "error": str(error), "reply": reply, "actions": titles}
        finally:
            self.busy = False

    def _start_live(self) -> None:
        self._stop_live.clear()
        if self._live_thread and self._live_thread.is_alive():
            try:
                self.camera.set_overlay_preview(True)
            except Exception:
                pass
            return
        self._pilot.reset()
        self._operator.reset()
        self._body.reset()
        self._operator_was_locked = False
        try:
            self.camera.set_overlay_preview(True)
        except Exception:
            pass
        self._live_thread = threading.Thread(target=self._live_loop, daemon=True)
        self._live_thread.start()

    def _stop_live_loop(self) -> None:
        self._stop_live.set()
        try:
            self.camera.set_overlay_preview(False)
        except Exception:
            pass

    def _live_loop(self) -> None:
        try:
            import cv2
        except Exception:
            cv2 = None
        last_print = ""
        while not self._stop_live.is_set():
            frame = self._prepared_frame()
            if self.mode == "imitate":
                self._imitate_frame(frame)
                time.sleep(0.05)
                continue
            if self.mode == "greet":
                self._greet_frame(frame)
                time.sleep(0.06)
                continue
            hands: list = []
            persons: list = []
            owned: list = []
            landmarks = None
            if self.camera_source == "r1":
                prev = self._body.status
                if frame is not None:
                    landmarks = self._detect_pose(frame)
                command = self._body.step(landmarks, time.time())
                if prev == "locked" and self._body.status == "hunting":
                    self._kick_gesture(GestureCommand("stop", label="丢失操作者", pose="none"))
                poses = [command.pose] if command.pose and command.pose != "none" else []
                op_info = {
                    "status": self._body.status,
                    "box": self._body.box,
                    "label": command.label,
                }
                status = self._body.status
            else:
                if frame is not None:
                    hands = self._detect_hands(frame)
                    if self._operator.enabled:
                        persons = self._detect_persons(frame)
                owned, op_info = self._operator.step(persons, hands)
                status = op_info["status"]
                if status == "hunting":
                    if self._operator_was_locked:
                        self._kick_gesture(GestureCommand("stop", label="丢失操作者", pose="none"))
                        self._pilot.reset()
                    command = GestureCommand("idle", label=op_info["label"] or "未检测到手", pose="none")
                    poses = [classify_hand(h) for h in hands]
                else:
                    use_hands = hands if status == "off" else owned
                    command = self._pilot.step(use_hands, time.time())
                    poses = [classify_hand(h) for h in use_hands]
                self._operator_was_locked = status == "locked"
            driving = self.mode == "gesture"
            issued = False
            skip = ""
            if driving:
                self.gesture_label = command.label
                issued, skip = self._kick_gesture(command)
            else:
                skip = "未开手势模式"
                self.gesture_label = f"preview {'/'.join(poses) or 'none'} | {command.label}"
            self.gesture_detail = {
                "poses": poses,
                "kind": command.kind,
                "label": command.label,
                "vx": float(command.vx),
                "vy": float(command.vy),
                "omega": float(command.omega),
                "operator": op_info["status"],
                "operator_label": op_info.get("label") or "",
                "strategy": "pose" if self.camera_source == "r1" else "hands",
                "issued": issued,
                "skip": skip,
            }
            line = (
                f"{self.gesture_label} vx={command.vx:.2f} vy={command.vy:.2f} om={command.omega:.2f}"
                f" issued={issued} {skip}"
            )
            if line != last_print:
                print(line, flush=True)
                last_print = line
            if frame is not None:
                try:
                    from r1_studio.camera import _encode, shrink_frame
                    from r1_studio.body import overlay_pose
                    from r1_studio.hands import overlay_detections, overlay_hands, overlay_operator

                    painted = shrink_frame(frame, 640).copy()
                    if self.camera_source == "r1":
                        painted = overlay_pose(painted, landmarks, self.gesture_label, self._body.box)
                    else:
                        painted = overlay_operator(
                            painted, persons, op_info.get("box"), op_info.get("status") or ""
                        )
                        painted = overlay_hands(
                            painted,
                            owned if status == "locked" else hands,
                            self.gesture_label,
                        )
                    painted = overlay_detections(painted, (self.last_vision or {}).get("items") or [])
                    self.camera.set_preview_jpeg(_encode(painted))
                    if self.preview_window and cv2 is not None and driving:
                        cv2.imshow("R1 laptop camera preview", painted)
                        cv2.waitKey(1)
                except Exception:
                    pass
            time.sleep(0.02)
        if cv2 is not None and self.preview_window:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass

    def _detection_view(self, frame):
        from r1_studio.depth import split_stereo

        left, _right = split_stereo(frame)
        return left if left is not None else frame

    def _greet_frame(self, frame) -> None:
        from r1_studio.camera import _encode, shrink_frame
        from r1_studio.depth import DistanceEstimate, LAPTOP_HFOV_DEG, R1_HFOV_DEG, estimate_distance, overlay_proximity
        from r1_studio.proximity import pick_pose

        view = self._detection_view(frame)
        boxes: list[tuple[float, float, float, float]] = []
        hands: list = []
        body_pose = "none"
        landmarks = None
        if view is not None:
            if self.camera_source == "r1":
                landmarks = self._detect_pose(view)
                if landmarks:
                    from r1_studio.body import classify_body

                    body_pose = classify_body(landmarks)
            else:
                hands = self._detect_hands(view)
                boxes = self._detect_persons(view)
        estimate, depth_preview = estimate_distance(
            frame if frame is not None else view,
            boxes,
            landmarks=landmarks,
            fov_deg=R1_HFOV_DEG if self.camera_source == "r1" else LAPTOP_HFOV_DEG,
        )
        pose = pick_pose(hands=hands, body_pose=body_pose)
        event = self._greet.step(estimate.meters, pose, time.time())
        note = event.note or "近距迎宾"
        self.greet_label = note
        self.greet_detail = {
            "distance_m": event.meters,
            "zone": event.zone,
            "source": estimate.source,
            "pose": pose,
            "note": note,
        }
        self.gesture_label = note
        self.gesture_detail = {
            "poses": [pose] if pose and pose != "none" else [],
            "kind": event.kind,
            "label": note,
            "vx": 0.0,
            "vy": 0.0,
            "omega": 0.0,
            "operator": event.zone,
            "operator_label": "" if estimate.meters is None else f"{estimate.meters:.2f} m",
            "strategy": "proximity",
            "issued": event.kind in ("greet", "gesture", "warn", "freeze") and bool(event.actions or event.reply),
            "skip": "" if event.kind != "idle" else note,
        }
        if event.kind == "freeze":
            try:
                self.backend.stop()
            except Exception:
                pass
            if event.reply:
                self._kick_greet(event)
        elif event.kind in ("greet", "gesture", "warn") and (event.actions or event.reply):
            self._kick_greet(event)
        if view is None:
            return
        try:
            shown = DistanceEstimate(event.meters, estimate.source, estimate.box, estimate.stereo)
            painted = overlay_proximity(
                shrink_frame(view, 640).copy(),
                shown,
                event.zone,
                note,
                depth_preview,
            )
            self.camera.set_preview_jpeg(_encode(painted))
        except Exception:
            pass

    def _kick_greet(self, event) -> None:
        if self._greet_busy:
            return
        self._greet_busy = True

        def run() -> None:
            try:
                self._apply_greet_event(event)
            finally:
                self._greet_busy = False

        threading.Thread(target=run, daemon=True).start()

    def _apply_greet_event(self, event) -> None:
        dist = "未知" if event.meters is None else f"{event.meters:.2f} 米"
        visual = f"[视觉] 同学大约在 {dist}，区={event.zone}，姿势={event.pose}。{event.note}"
        if event.kind == "freeze":
            try:
                self.backend.stop()
            except Exception:
                pass
            if event.reply:
                try:
                    self.backend.speak(event.reply)
                except Exception as error:
                    self.last_error = str(error)
                self.last_reply = event.reply
                self._remember_dialog(visual, event.reply, [])
            return
        if event.kind == "warn":
            if event.reply:
                try:
                    self.backend.speak(event.reply)
                except Exception as error:
                    self.last_error = str(error)
                self.last_reply = event.reply
                self._remember_dialog(visual, event.reply, [])
            return
        if event.kind in ("greet", "gesture") and (event.actions or event.reply):
            names = [name for name in event.actions if not str(name).startswith("say:")]
            spoken = event.reply
            self._remember_dialog(visual, spoken or event.note, list(event.actions))
            if spoken:
                try:
                    self.backend.speak(spoken)
                except Exception as error:
                    self.last_error = str(error)
            if names:
                self.run_names(names, reply=spoken or event.note)
            elif spoken:
                self.last_reply = spoken

    def _detect_hands(self, frame) -> list:
        try:
            if self._hands is None:
                from r1_studio.hands import HandTracker

                self._hands = HandTracker(num_hands=4 if self._operator.enabled else 2)
            return self._hands.detect_bgr(frame)
        except Exception as error:
            self.gesture_label = f"手势模型未就绪：{error}"
            return []

    def _detect_pose(self, frame):
        image, _world = self._detect_pose_pair(frame)
        return image

    def _detect_pose_pair(self, frame) -> tuple:
        try:
            if self._pose is None:
                from r1_studio.body import PoseTracker

                self._pose = PoseTracker()
            if hasattr(self._pose, "detect_pair"):
                return self._pose.detect_pair(frame)
            return self._pose.detect_bgr(frame), None
        except Exception as error:
            self.gesture_label = f"全身 Pose 未就绪：{error}"
            self.imitate_label = f"全身 Pose 未就绪：{error}"
            return None, None

    def _imitate_frame(self, frame) -> None:
        from r1_studio.camera import _encode, shrink_frame
        from r1_studio.body import overlay_pose

        image_lm = None
        status = "未看到全身"
        if frame is not None:
            image_lm, world = self._detect_pose_pair(frame)
            if world:
                try:
                    from imitate.pose_to_arm import landmarks_to_arm_rad, mediapipe_world_to_array
                    from imitate.retarget import retarget_to_ready

                    pose = retarget_to_ready(landmarks_to_arm_rad(mediapipe_world_to_array(world)))
                    self.backend.track_arm(pose, 0.05)
                    status = "正在跟臂（人右手→机器人左臂）"
                except Exception as error:
                    status = str(error)
            elif image_lm:
                status = "看到骨架，世界坐标还不够，请整个人进画面"
        self.imitate_label = status
        self.gesture_label = status
        if frame is None:
            return
        try:
            painted = overlay_pose(shrink_frame(frame, 640).copy(), image_lm, status)
            self.camera.set_preview_jpeg(_encode(painted))
        except Exception:
            pass

    def _detect_persons(self, frame) -> list[tuple[float, float, float, float]]:
        self._person_tick += 1
        if self._last_persons and self._person_tick % 4:
            return self._last_persons
        try:
            from r1_studio.vision import person_boxes

            if self._detector is None:
                from r1_studio.vision import MediaPipeObjectDetector

                self._detector = MediaPipeObjectDetector()
            self._last_persons = person_boxes(self._detector.detect_bgr(frame))
        except Exception:
            pass
        return self._last_persons

    def _kick_gesture(self, command: GestureCommand) -> tuple[bool, str]:
        if command.kind == "idle":
            return False, "识别是悬停，不会下发走路"
        if self._gesture_busy:
            return False, "上一条指令还在发给机器人"
        self._gesture_busy = True

        def run() -> None:
            try:
                self._apply_gesture(command)
            finally:
                self._gesture_busy = False

        threading.Thread(target=run, daemon=True).start()
        return True, "已交给机器人线程"

    def _apply_gesture(self, command: GestureCommand) -> tuple[bool, str]:
        try:
            if command.kind == "idle":
                return False, "识别是悬停，不会下发走路"
            if command.kind == "stop":
                self.drive(0.0, 0.0, 0.0)
                return True, "停"
            if command.kind == "drive":
                now = time.time()
                gap = 0.9 if abs(command.vy) >= 0.05 else 0.45
                if now - self._last_gesture_drive < gap:
                    return False, "节流中，沿用上一条速度"
                self._last_gesture_drive = now
                result = self.drive(command.vx, command.vy, command.omega)
                if not result.get("ok"):
                    return False, str(result.get("error") or "SetVelocity 失败")
                print(
                    f"APPLY SetVelocity vx={command.vx:.2f} vy={command.vy:.2f} om={command.omega:.2f}",
                    flush=True,
                )
                return True, ""
            if command.kind == "cheer":
                if self.busy:
                    return False, "上一条动作还在执行"
                self.run_names(["cheer_both"], reply="比耶！双手欢呼")
                return True, "欢呼"
            return False, command.kind
        except Exception as error:
            self.last_error = str(error)
            return False, str(error)
