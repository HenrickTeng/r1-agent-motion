"""笔记本摄像头 + MediaPipe Pose（Tasks 1.0）→ 实时关节角 + MuJoCo 跟臂。"""

from __future__ import annotations

import math
import time
import urllib.request
from pathlib import Path
from typing import Mapping

from imitate.calibrate import (
    CALIB_DEMO_S,
    CALIB_POSES,
    CALIB_SAMPLES,
    fit_joint_scales,
    mean_pose_rad,
    save_calibration,
    write_standing_ik,
)
from imitate.capture import _fmt_pose, attach_collision, build_action, save_action
from imitate.joints import ARM_JOINTS
from imitate.limits import ElectronicLimits
from imitate.pose_to_arm import (
    PoseSmoother,
    landmarks_to_arm_rad,
    mediapipe_world_to_array,
)
from imitate.retarget import retarget_to_ready, teacher_pose_rad
from imitate.sim import ArmSim

HERE = Path(__file__).resolve().parent
MODEL_PATH = HERE / "assets" / "pose_landmarker_lite.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)
ARM_LANDMARKS = (11, 12, 13, 14, 15, 16, 23, 24)


def ensure_pose_model() -> Path:
    if MODEL_PATH.is_file() and MODEL_PATH.stat().st_size > 100_000:
        return MODEL_PATH
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"下载 MediaPipe Pose 模型 → {MODEL_PATH}")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    return MODEL_PATH


def _arm_visible(world_landmarks: list) -> bool:
    if len(world_landmarks) < 25:
        return False
    for index in ARM_LANDMARKS:
        visibility = getattr(world_landmarks[index], "visibility", None)
        if visibility is not None and visibility < 0.4:
            return False
    return True


WINDOW = "R1 cam"
PREVIEW_W, PREVIEW_H = 400, 225
CAM_CAPTURE_W, CAM_CAPTURE_H = 640, 360
POSE_SCRIPT = (
    "1 下垂",
    "2 侧平举",
    "3 前伸(朝镜头)",
    "4 抱胸(胸前两侧,不交叉)",
    "5 右手上举 左手下垂",
)
COACH_LESSONS = (
    ("down", "1 双手下垂"),
    ("tpose", "2 双臂侧平举(肘微屈)"),
    ("forward", "3 双臂前平举(肘微屈)"),
    ("hands_chest", "4 双手胸前两侧(不交叉)"),
    ("raise_user_right", "5 人举右手→机器人蓝臂/左"),
    ("salute_user_right", "6 人右手敬礼→机器人蓝臂/左"),
)
COACH_DEMO_S = 5.0
COACH_SAMPLES = 3
COACH_HOLD_S = 1.4
COACH_COOLDOWN_S = 0.8
HOLD_CAPTURE_S = 1.6
HOLD_SAVE_S = 2.2
COOLDOWN_S = 0.4
POSE_CHANGE_RAD = 0.40


def _open_preview_window(cv2) -> None:
    """小窗、可拖、可拉，避免挡住 MuJoCo。"""
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW, PREVIEW_W, PREVIEW_H)
    cv2.moveWindow(WINDOW, 24, 24)


def _script_hint(captured: int) -> str:
    if captured >= len(POSE_SCRIPT):
        return "5 frames done — close window to save"
    return POSE_SCRIPT[captured]


def _pose_delta(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    return max(abs(float(a[name]) - float(b[name])) for name in ARM_JOINTS if name in a and name in b)


def _both_hands_up(pose: Mapping[str, float]) -> bool:
    return (
        math.degrees(pose["left_shoulder_pitch"]) < -120
        and math.degrees(pose["right_shoulder_pitch"]) < -120
    )


def _arm_shape(pose: Mapping[str, float]) -> str:
    lp = math.degrees(pose["left_shoulder_pitch"])
    rp = math.degrees(pose["right_shoulder_pitch"])
    lr = math.degrees(pose["left_shoulder_roll"])
    rr = math.degrees(pose["right_shoulder_roll"])
    if lp < -50 and rp < -50 and abs(lr) < 35 and abs(rr) < 35:
        return "FORWARD"
    if abs(lp) < 35 and abs(rp) < 35 and lr > 45 and rr < -45:
        return "TPOSE"
    if abs(lp) < 30 and abs(rp) < 30 and abs(lr) < 25 and abs(rr) < 25:
        return "DOWN"
    return "OTHER"


def run_camera(
    camera: int,
    *,
    mirror: bool = True,
    mujoco_view: bool = True,
    capture: bool = True,
    full_model: bool = False,
    hardware: bool = False,
    interface: str = "auto",
    r1_stream: bool = False,
) -> None:
    try:
        import cv2
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
    except ImportError as error:
        raise SystemExit("摄像头模式需要: pip install mediapipe opencv-python") from error

    model = ensure_pose_model()
    options = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model)),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = vision.PoseLandmarker.create_from_options(options)

    sim = ArmSim(preview_only=not full_model)
    limiter = ElectronicLimits(sim)
    smoother = PoseSmoother(alpha=0.35)
    frames: list[dict] = []
    if r1_stream:
        from imitate.r1_video import R1VideoCapture

        cap = R1VideoCapture(interface)
    else:
        cap = cv2.VideoCapture(camera)
        if not cap.isOpened():
            landmarker.close()
            raise SystemExit(f"打不开摄像头 {camera}。换 --camera 1 或检查权限。")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_CAPTURE_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_CAPTURE_H)
    if not cap.isOpened():
        landmarker.close()
        raise SystemExit("打不开视频源。")
    _open_preview_window(cv2)

    viewer = None
    if mujoco_view:
        try:
            import mujoco.viewer
            viewer = mujoco.viewer.launch_passive(sim.model, sim.data)
        except Exception as error:
            print(f"MuJoCo 窗口未打开（仍可看摄像头）: {error}")

    if capture:
        print("一个人也能测：不用碰键盘。同一姿势只采一帧，换动作后再采。")
        print("  动作顺序：")
        for line in POSE_SCRIPT:
            print(f"    {line}")
        print("  第4步双手停在胸前左右，不要交叉、不要贴太近。")
        print("  站稳约 1.6 秒采帧；画面出现 next 再换下一个；关窗口自动保存")
    else:
        if hardware:
            print("真机跟臂：软件限位开着。红字 LIMIT = 挡自碰。关窗口退出。")
        else:
            print("只开图传+骨架，不采帧、不发 arm_sdk。关窗口退出。")
    robot = None
    last_hw_t = time.time()
    if hardware:
        from r1_agent.dds_robot import DdsRobot

        print("真机跟臂：遥控器物理急停必须在手。")
        print("  软急停 E 或空格（只跟臂时）→ StopMove + 锁住当前臂，不进 Damp。")
        print("  恢复 R · 退出 Q（会缓慢交还 arm_sdk 权重）")
        robot = DdsRobot(interface)
        robot.require_walk_run()
        print(f"  网卡 {robot._interface}，fsm 811，软件限位开着，慢速回待机…")
        robot.goto_ready(3.5)
        print("  已到待机，开始跟臂。")
        last_hw_t = time.time()
    t0 = time.time()
    last_log = ""
    hold_pose: dict[str, float] | None = None
    hold_since = 0.0
    last_captured: dict[str, float] | None = None
    hands_up_since = 0.0
    cooldown_until = 0.0
    click = {"capture": False}
    hint = POSE_SCRIPT[0]

    def on_mouse(_event, _x, _y, *_rest):
        import cv2 as _cv

        if _event == _cv.EVENT_LBUTTONDOWN:
            click["capture"] = True

    def persist(reason: str) -> None:
        if not frames:
            return
        payload = build_action(f"capture_{int(time.time())}", "摄像头采集", list(frames))
        attach_collision(payload, sim)
        path = save_action(payload)
        print(f"  {reason} 已保存 {path}（{len(frames)} 帧）")
        frames.clear()

    named = False
    try:
        while viewer is None or viewer.is_running():
            ok, image = cap.read()
            if not ok:
                print("摄像头读帧失败，重试…")
                time.sleep(0.05)
                continue
            if mirror:
                image = cv2.flip(image, 1)
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            timestamp_ms = int((time.time() - t0) * 1000)
            result = landmarker.detect_for_video(mp_image, timestamp_ms)

            pose_rad = None
            status = "no pose"
            if result.pose_landmarks and result.pose_world_landmarks:
                vision.drawing_utils.draw_landmarks(
                    image,
                    result.pose_landmarks[0],
                    vision.PoseLandmarksConnections.POSE_LANDMARKS,
                )
                world = result.pose_world_landmarks[0]
                if _arm_visible(world):
                    ik = retarget_to_ready(landmarks_to_arm_rad(mediapipe_world_to_array(world)))
                    pose_rad, sample, limited = limiter.apply(smoother.update(ik))
                    sim.set_pose(pose_rad)
                    if viewer is not None:
                        viewer.sync()
                    ik_shape = _arm_shape(ik)
                    out_shape = _arm_shape(pose_rad)
                    if limited:
                        color = (0, 0, 220)
                        status = f"LIMIT {sample.status} {sample.minimum_distance_m*1000:.0f}mm"
                    else:
                        color = (40, 200, 40)
                        status = f"SAFE {sample.minimum_distance_m*1000:.0f}mm"
                    status = f"IK {ik_shape}  OUT {out_shape}  {status}"
                    log = f"{ik_shape}->{out_shape} {'LIMIT' if limited else 'OK'} {sample.status}"
                    if log != last_log:
                        print(f"{log}  {_fmt_pose(ik)}")
                        last_log = log
                    cv2.putText(image, f"IK  {ik_shape}  {_fmt_pose(ik)}", (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (80, 220, 255), 2)
                    cv2.putText(image, f"OUT {out_shape}  {_fmt_pose(pose_rad)}", (16, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
                else:
                    smoother.reset()
                    status = "arms not visible"
                    hold_pose = None
                    hands_up_since = 0.0
            else:
                smoother.reset()
                hold_pose = None
                hands_up_since = 0.0

            now = time.time()
            want_capture = False
            want_save = False
            if capture:
                want_capture = click["capture"]
                click["capture"] = False
                same_as_last = (
                    last_captured is not None
                    and pose_rad is not None
                    and _pose_delta(pose_rad, last_captured) < POSE_CHANGE_RAD
                )
                if pose_rad is not None and now >= cooldown_until and not same_as_last:
                    if hold_pose is None or _pose_delta(pose_rad, hold_pose) > 0.12:
                        hold_pose = dict(pose_rad)
                        hold_since = now
                        hint = "new pose — hold still"
                    else:
                        held = now - hold_since
                        remain = HOLD_CAPTURE_S - held
                        hint = f"hold {remain:.1f}s  {_script_hint(len(frames))}" if remain > 0 else "capturing"
                        if held >= HOLD_CAPTURE_S:
                            want_capture = True
                    if _both_hands_up(pose_rad):
                        if hands_up_since == 0.0:
                            hands_up_since = now
                        up_remain = HOLD_SAVE_S - (now - hands_up_since)
                        if up_remain > 0:
                            hint = f"hands up: save in {up_remain:.1f}s"
                        else:
                            want_save = True
                    else:
                        hands_up_since = 0.0
                elif pose_rad is None:
                    hint = "step into camera"
                elif same_as_last:
                    hint = f"ok #{len(frames)}  next: {_script_hint(len(frames))}"
            else:
                hint = "record: follow only, close window to quit"

            if capture and want_capture and pose_rad is not None:
                frames.append(dict(pose_rad))
                last_captured = dict(pose_rad)
                cooldown_until = now + COOLDOWN_S
                hold_pose = None
                hint = f"ok #{len(frames)}  next: {_script_hint(len(frames))}"
                print(f"  keyframe {len(frames)}  {status}")
            if want_save:
                persist("双手举高")
                cooldown_until = now + COOLDOWN_S
                hands_up_since = 0.0

            if robot is not None:
                now_hw = time.time()
                dt = now_hw - last_hw_t
                last_hw_t = now_hw
                try:
                    robot.track_arm(pose_rad or {}, dt)
                except RuntimeError as error:
                    print("hardware:", error)
                    robot.soft_estop()
                if robot._estop:
                    cv2.putText(
                        image,
                        "SOFT ESTOP  R=resume",
                        (8, 110),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (0, 0, 220),
                        2,
                    )

            cv2.putText(
                image,
                f"{status} | {hint}",
                (16, 84),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (240, 240, 240),
                2,
            )
            cv2.imshow(WINDOW, image)
            if not named:
                cv2.setMouseCallback(WINDOW, on_mouse)
                named = True
            visible = cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE)
            if named and visible >= 0 and visible < 0.5:
                if capture:
                    persist("关窗")
                break
            key = cv2.waitKey(1) & 0xFF
            if robot is not None and key in (ord("e"), ord("E")):
                robot.soft_estop()
                print("  SOFT ESTOP")
            if robot is not None and (not capture) and key == ord(" "):
                robot.soft_estop()
                print("  SOFT ESTOP")
            if robot is not None and key in (ord("r"), ord("R")):
                robot.clear_estop()
                print("  estop cleared")
            if key in (ord("q"), 27):
                if capture:
                    persist("退出")
                break
            if capture and key == ord(" ") and pose_rad is not None:
                frames.append(dict(pose_rad))
                print(f"  keyframe {len(frames)}  {status}")
            if capture and key in (ord("c"), ord("C")):
                frames.clear()
                print("  已清空关键帧")
            if capture and key in (ord("s"), ord("S")):
                persist("按键")
        if capture:
            persist("结束")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        landmarker.close()
        if robot is not None:
            try:
                robot._release()
            except Exception:
                pass
        if viewer is not None:
            viewer.close()


def run_coach(camera: int, *, mirror: bool = True, full_model: bool = False, calibrate: bool = False) -> None:
    """模型先演示，再模仿采 3 帧。calibrate=True 时示范 15 秒、无动作名，并写入校准文件。"""
    try:
        import cv2
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
    except ImportError as error:
        raise SystemExit("需要: pip install mediapipe opencv-python") from error

    model = ensure_pose_model()
    options = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model)),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = vision.PoseLandmarker.create_from_options(options)
    sim = ArmSim(preview_only=not full_model)
    limiter = ElectronicLimits(sim)
    smoother = PoseSmoother(alpha=0.35)
    frames: list[dict] = []
    cap = cv2.VideoCapture(camera)
    if not cap.isOpened():
        landmarker.close()
        raise SystemExit(f"打不开摄像头 {camera}。")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_CAPTURE_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_CAPTURE_H)
    _open_preview_window(cv2)
    try:
        import mujoco.viewer
        viewer = mujoco.viewer.launch_passive(sim.model, sim.data)
        viewer.cam.lookat[:] = (0.02, 0.0, 0.85)
        viewer.cam.distance = 2.6 if full_model else 1.8
        viewer.cam.azimuth = 145
        viewer.cam.elevation = -18
    except Exception as error:
        landmarker.close()
        cap.release()
        raise SystemExit(f"需要 MuJoCo 窗口做演示: {error}") from error

    lessons = tuple((name, "") for name in CALIB_POSES) if calibrate else COACH_LESSONS
    demo_s = CALIB_DEMO_S if calibrate else COACH_DEMO_S
    n_samples = CALIB_SAMPLES if calibrate else COACH_SAMPLES
    teacher = {name: teacher_pose_rad(name) for name, _title in lessons}
    print(f"模型: {sim.model_path}")
    if calibrate:
        print("校准：只看 MuJoCo 里的 R1，小窗无动作名。换摄像头或换人请重新跑。")
        print(f"每个姿势：示范 {demo_s:.0f} 秒 → 模仿并站稳采 {n_samples} 帧。共 {len(lessons)} 个。")
        print("  做完写入 imitate/assets/calibration.json 和 standing_ik_deg.json")
    else:
        print("教练模式：摄像头是小窗，请把 MuJoCo 放到最大。")
        print("每个动作两段（以模型画面为准，不必按文字字面）：")
        print("  1) 黄字：只看大窗口里的 R1，这时不采帧")
        print("  2) 绿字：模仿刚才 R1 摆出来的姿势，站稳连采 3 帧")
        for index, (_name, title) in enumerate(lessons, start=1):
            print(f"  {index}/{len(lessons)}  {title}")
    print("  关窗口可随时结束。")

    lesson = 0
    phase = "demo"
    phase_t0 = time.time()
    samples = 0
    hold_pose: dict[str, float] | None = None
    hold_since = 0.0
    cooldown_until = 0.0
    t0 = time.time()
    last_log = ""
    last_raw: dict[str, float] | None = None

    raw_by_pose: dict[str, list[dict[str, float]]] = {name: [] for name, _t in lessons}

    def persist() -> None:
        if calibrate:
            if not any(raw_by_pose.values()):
                return
            means = {name: mean_pose_rad(frames) for name, frames in raw_by_pose.items() if frames}
            if "down" not in means:
                print("  校准未采到第 1 个姿势，未写入。")
                return
            standing = means["down"]
            scales = fit_joint_scales(standing, means)
            path = save_calibration(
                camera=camera,
                standing_rad=standing,
                pose_means_rad=means,
                scales=scales,
                raw_by_pose={name: frames for name, frames in raw_by_pose.items() if frames},
            )
            print(f"  已写入校准 {path}")
            for name, scale in scales.items():
                if abs(scale - 1.0) > 0.05:
                    print(f"    scale {name}={scale:.2f}")
            for name in raw_by_pose:
                raw_by_pose[name] = []
            return
        if not frames:
            return
        payload = build_action(f"coach_{int(time.time())}", "教练模式采集", list(frames))
        attach_collision(payload, sim)
        path = save_action(payload)
        print(f"  已保存 {path}（{len(frames)} 帧）")
        frames.clear()

    try:
        while viewer.is_running():
            ok, image = cap.read()
            if not ok:
                break
            if mirror:
                image = cv2.flip(image, 1)
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = landmarker.detect_for_video(mp_image, int((time.time() - t0) * 1000))
            now = time.time()
            name, title = lessons[min(lesson, len(lessons) - 1)]
            done = lesson >= len(lessons)
            pose_rad = None
            status = "no pose"
            if result.pose_landmarks:
                vision.drawing_utils.draw_landmarks(
                    image,
                    result.pose_landmarks[0],
                    vision.PoseLandmarksConnections.POSE_LANDMARKS,
                )
            if (
                not done
                and phase != "demo"
                and result.pose_world_landmarks
                and _arm_visible(result.pose_world_landmarks[0])
            ):
                raw = landmarks_to_arm_rad(mediapipe_world_to_array(result.pose_world_landmarks[0]))
                last_raw = dict(raw)
                ik = retarget_to_ready(raw)
                pose_rad, sample, limited = limiter.apply(smoother.update(ik))
                status = (
                    f"LIMIT {sample.status} {sample.minimum_distance_m*1000:.0f}mm"
                    if limited
                    else f"SAFE {sample.minimum_distance_m*1000:.0f}mm"
                )
                label = f"{lesson+1}/{len(lessons)}" if calibrate else title
                log = f"{label} {phase} {_arm_shape(ik)} {status}"
                if log != last_log:
                    print(log, _fmt_pose(ik))
                    last_log = log
            elif phase == "demo":
                status = "demo"
            else:
                smoother.reset()

            if done:
                hint = "全部完成 关掉窗口"
                color = (40, 200, 40)
            elif phase == "demo":
                sim.set_pose(teacher[name])
                remain = demo_s - (now - phase_t0)
                elapsed = max(0.0, now - phase_t0)
                viewer.cam.azimuth = 145.0 + 360.0 * min(1.0, elapsed / max(demo_s, 0.01))
                viewer.cam.lookat[:] = (0.02, 0.0, 0.85)
                viewer.cam.distance = 2.6 if full_model else 1.8
                viewer.cam.elevation = -18
                step = f"{lesson+1}/{len(lessons)}" if calibrate else f"{lesson+1}/{len(lessons)} {title}"
                hint = f"{step}  看R1  {max(0.0, remain):.1f}s"
                color = (80, 220, 255)
                if remain <= 0:
                    phase = "imitate"
                    samples = 0
                    hold_pose = None
                    cooldown_until = now + 0.4
                    smoother.reset()
                    print(f"  → {step} 模仿窗口里的 R1（{n_samples} 次）")
            else:
                step = f"{lesson+1}/{len(lessons)}" if calibrate else f"{lesson+1}/{len(lessons)} {title}"
                if pose_rad is not None:
                    sim.set_pose(pose_rad)
                    if now >= cooldown_until:
                        if hold_pose is None or _pose_delta(pose_rad, hold_pose) > 0.12:
                            hold_pose = dict(pose_rad)
                            hold_since = now
                            hint = f"{step}  模仿  {samples+1}/{n_samples}  站稳"
                        else:
                            remain = COACH_HOLD_S - (now - hold_since)
                            hint = f"{step}  模仿  {samples+1}/{n_samples}  站稳 {max(0.0, remain):.1f}s"
                            if remain <= 0:
                                frames.append(dict(pose_rad))
                                if calibrate and last_raw is not None:
                                    raw_by_pose[name].append(dict(last_raw))
                                samples += 1
                                print(f"  采样 {step} {samples}/{n_samples}  {status}")
                                hold_pose = None
                                cooldown_until = now + COACH_COOLDOWN_S
                                if samples >= n_samples:
                                    if calibrate and name == "down" and raw_by_pose["down"]:
                                        write_standing_ik(mean_pose_rad(raw_by_pose["down"]))
                                        print("  已更新垂臂零位 standing_ik")
                                    lesson += 1
                                    if lesson >= len(lessons):
                                        persist()
                                        print("  六个姿势都采完了。")
                                    else:
                                        phase = "demo"
                                        phase_t0 = now
                                        smoother.reset()
                    else:
                        hint = f"{step}  模仿  {samples+1}/{n_samples}"
                else:
                    hint = f"{step}  请入画"
                color = (40, 200, 40)

            if viewer is not None:
                viewer.sync()
            cv2.putText(image, hint, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
            cv2.putText(image, status, (8, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (240, 240, 240), 1)
            cv2.imshow(WINDOW, image)
            if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 0.5:
                persist()
                break
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                persist()
                break
    finally:
        persist()
        cap.release()
        cv2.destroyAllWindows()
        landmarker.close()
        viewer.close()
