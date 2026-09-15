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
from r1_studio.vision import (
    Detection,
    ask_campus,
    is_vision_intent,
    load_campus_text,
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
            },
            "groups": self.custom_groups,
            "presets": PRESETS,
        }

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
        if mode not in ("idle", "teleop", "gesture", "vision", "blocks"):
            raise ProgramError("未知模式")
        previous = self.mode
        self.mode = mode
        if mode == "gesture":
            self.busy = False
            self._last_gesture_drive = 0.0
            self._operator.reset()
            self._body.reset()
            self._start_live()
            self.gesture_label = (
                "请侧平举或双手上举，用全身姿势锁定"
                if self.camera_source == "r1"
                else "手势操作已开启"
            )
            if previous in ("teleop", "blocks"):
                threading.Thread(target=self._stop_backend_quiet, daemon=True).start()
            return
        self._stop_live_loop()
        if self._live_thread is not None and not self._live_thread.is_alive():
            self._live_thread = None
        self.busy = False
        with self._twist_lock:
            self._want_move = False
        self.gesture_label = "手势未开启"
        self.last_error = ""
        if mode == "teleop":
            self.last_reply = "键盘遥控已开启。请先点一下旁边的 QWEASD 格子，浏览器才会接收按键。"
        if previous in ("gesture", "teleop") or mode == "idle":
            threading.Thread(target=self._stop_backend_quiet, daemon=True).start()

    def _stop_backend_quiet(self) -> None:
        try:
            self.backend.stop()
        except Exception:
            pass

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
        if self.mode != "teleop":
            return {"ok": False, "error": "请先点「开始键盘遥控」", "vx": 0.0, "vy": 0.0, "omega": 0.0, "duration": 0.0}
        self.busy = False
        vx, vy, omega = keys_to_twist(keys, slow=slow)
        return self.drive(vx, vy, omega)

    def drive(self, vx: float, vy: float, omega: float) -> dict:
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

    def handle_text(self, text: str, *, speak_reply: bool | None = None) -> dict:
        text = text.strip()
        if not text:
            return {"ok": False, "error": "空文本"}
        if self.mode == "vision" or is_vision_intent(text):
            return self.capture_vision(speak=True, question=text)
        use_deepseek = bool(self.llm_key or load_deepseek_key())
        planner = (
            DeepSeekPlanner(
                self.catalog,
                api_url=self.llm_url,
                model=self.llm_model,
                api_key=self.llm_key,
            )
            if use_deepseek
            else RulePlanner(self.catalog)
        )
        try:
            reply, actions = planner.plan(text)
        except Exception as error:
            reply, actions = RulePlanner(self.catalog).plan(text)
            self.last_error = str(error)
        speak = self.hardware if speak_reply is None else speak_reply
        result = self._execute(actions, reply, speak=speak)
        result["heard"] = text
        return result

    def listen_once(self) -> dict:
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
        try:
            if self._pose is None:
                from r1_studio.body import PoseTracker

                self._pose = PoseTracker()
            return self._pose.detect_bgr(frame)
        except Exception as error:
            self.gesture_label = f"全身 Pose 未就绪：{error}"
            return None

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
