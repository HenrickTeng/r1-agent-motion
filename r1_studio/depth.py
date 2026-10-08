"""近距迎宾用的距离估计：能拆左右目就做视差深度图，否则用人体框高度估距。"""

from __future__ import annotations

from dataclasses import dataclass

DANGER_M = 0.30
CAUTION_M = 0.50
GREET_MIN_M = 0.50
GREET_MAX_M = 1.80
PERSON_HEIGHT_M = 1.65
# 机载超广角：把 Pose 的肩宽/躯干当「全身 1.65 m」会把距离放大好几倍。
SHOULDER_WIDTH_M = 0.38
TORSO_LENGTH_M = 0.52
R1_HFOV_DEG = 120.0
LAPTOP_HFOV_DEG = 70.0
# R1 头部双目大约 6 cm；没有标定文件时用这个数量级。
DEFAULT_BASELINE_M = 0.06
L_SH, R_SH, L_HIP, R_HIP, NOSE, L_ANKLE, R_ANKLE = 11, 12, 23, 24, 0, 27, 28


@dataclass(frozen=True)
class DistanceEstimate:
    meters: float | None
    source: str
    box: tuple[float, float, float, float] | None = None
    stereo: bool = False


def looks_side_by_side(frame) -> bool:
    if frame is None:
        return False
    height, width = frame.shape[:2]
    return width >= 2 * height and width >= 160


def split_stereo(frame):
    """宽画幅按左右对半拆。单目则右图为 None。"""
    if frame is None:
        return None, None
    if not looks_side_by_side(frame):
        return frame, None
    width = frame.shape[1] // 2
    return frame[:, :width], frame[:, width : width * 2]


def focal_px(width: int, *, fov_deg: float = 70.0) -> float:
    import math

    half = math.tan(math.radians(fov_deg) / 2.0)
    return (max(1, width) / 2.0) / max(half, 1e-3)


def disparity_to_depth_m(disparity: float, *, fx: float, baseline_m: float = DEFAULT_BASELINE_M) -> float | None:
    if disparity <= 0.15 or fx <= 0 or baseline_m <= 0:
        return None
    return float(fx * baseline_m / disparity)


def bbox_distance_m(
    box: tuple[float, float, float, float],
    frame_height: int,
    *,
    person_height_m: float = PERSON_HEIGHT_M,
    fy: float | None = None,
    frame_width: int = 640,
) -> float | None:
    x1, y1, x2, y2 = box
    height_frac = max(0.0, y2 - y1)
    if height_frac < 0.05:
        return None
    pix = height_frac * max(1, frame_height)
    focus = fy if fy is not None else focal_px(frame_width)
    meters = float(person_height_m * focus / pix)
    if meters < 0.08 or meters > 8.0:
        return None
    return meters


def _lm_xy(landmarks, index: int) -> tuple[float, float] | None:
    if not landmarks or index >= len(landmarks):
        return None
    point = landmarks[index]
    if isinstance(point, dict):
        return float(point["x"]), float(point["y"])
    return float(point.x), float(point.y)


def _visible(landmarks, index: int, *, min_vis: float = 0.35) -> bool:
    if not landmarks or index >= len(landmarks):
        return False
    point = landmarks[index]
    vis = getattr(point, "visibility", None)
    if vis is None and isinstance(point, dict):
        vis = point.get("visibility")
    if vis is None:
        return True
    return float(vis) >= min_vis


def pose_span_box(landmarks) -> tuple[float, float, float, float] | None:
    xs, ys = [], []
    for index in (NOSE, L_SH, R_SH, L_HIP, R_HIP, L_ANKLE, R_ANKLE, 13, 14, 15, 16):
        if not _visible(landmarks, index, min_vis=0.2):
            continue
        xy = _lm_xy(landmarks, index)
        if xy is None:
            continue
        xs.append(xy[0])
        ys.append(xy[1])
    if len(xs) < 4:
        return None
    return (
        max(0.0, min(xs) - 0.04),
        max(0.0, min(ys) - 0.06),
        min(1.0, max(xs) + 0.04),
        min(1.0, max(ys) + 0.06),
    )


def pose_distance_m(
    landmarks,
    frame_width: int,
    frame_height: int,
    *,
    fov_deg: float = R1_HFOV_DEG,
) -> tuple[float | None, str]:
    """用肩宽或肩-髋长度估距。不要把半身框当成 1.65 m 全身。"""
    if not landmarks or frame_width < 8 or frame_height < 8:
        return None, "no-pose"
    fx = focal_px(frame_width, fov_deg=fov_deg)
    candidates: list[tuple[float, str]] = []
    lsh = _lm_xy(landmarks, L_SH) if _visible(landmarks, L_SH) else None
    rsh = _lm_xy(landmarks, R_SH) if _visible(landmarks, R_SH) else None
    if lsh and rsh:
        shoulder_px = abs(rsh[0] - lsh[0]) * frame_width
        if shoulder_px >= 12:
            meters = SHOULDER_WIDTH_M * fx / shoulder_px
            if 0.12 <= meters <= 6.5:
                candidates.append((meters, "pose-shoulder"))
    lhp = _lm_xy(landmarks, L_HIP) if _visible(landmarks, L_HIP) else None
    rhp = _lm_xy(landmarks, R_HIP) if _visible(landmarks, R_HIP) else None
    if lsh and rsh and lhp and rhp:
        mid_sh = ((lsh[0] + rsh[0]) / 2, (lsh[1] + rsh[1]) / 2)
        mid_hp = ((lhp[0] + rhp[0]) / 2, (lhp[1] + rhp[1]) / 2)
        torso_px = abs(mid_hp[1] - mid_sh[1]) * frame_height
        if torso_px >= 16:
            meters = TORSO_LENGTH_M * fx / torso_px
            if 0.12 <= meters <= 6.5:
                candidates.append((meters, "pose-torso"))
    nose = _lm_xy(landmarks, NOSE) if _visible(landmarks, NOSE, min_vis=0.25) else None
    lank = _lm_xy(landmarks, L_ANKLE) if _visible(landmarks, L_ANKLE, min_vis=0.25) else None
    rank = _lm_xy(landmarks, R_ANKLE) if _visible(landmarks, R_ANKLE, min_vis=0.25) else None
    foot = lank or rank
    if nose and foot:
        height_px = abs(foot[1] - nose[1]) * frame_height
        if height_px >= 40:
            meters = PERSON_HEIGHT_M * fx / height_px
            if 0.12 <= meters <= 6.5:
                candidates.append((meters, "pose-height"))
    if not candidates:
        return None, "pose-weak"
    # 肩宽在正面最稳；侧面肩宽会偏远，若躯干更近则采用更近的。
    candidates.sort(key=lambda item: item[0])
    nearest, near_src = candidates[0]
    shoulder = next((item for item in candidates if item[1] == "pose-shoulder"), None)
    if shoulder and shoulder[0] < nearest * 1.8:
        return shoulder[0], shoulder[1]
    return nearest, near_src


def pair_from_shift(frame, shift_px: int = 16):
    """单目画面左右裁同一位移，用来验收 SGBM 流水线（不是真双目）。"""
    if frame is None:
        return None, None
    shift_px = int(shift_px)
    if shift_px < 1 or frame.shape[1] <= shift_px + 16:
        return frame, None
    return frame[:, :-shift_px], frame[:, shift_px:]


def inspect_stereo(
    frame,
    *,
    shift_px: int = 16,
    fov_deg: float = R1_HFOV_DEG,
    baseline_m: float = DEFAULT_BASELINE_M,
) -> tuple[dict, object]:
    """看机载是不是左右拼图，并用平移视差检查 SGBM 能否找回位移。"""
    info: dict = {
        "ok": False,
        "native_sbs": False,
        "shape": None,
        "shift_px": int(shift_px),
        "disparity_median": None,
        "pipeline_ok": False,
        "depth_m_if_baseline_6cm": None,
        "note": "",
    }
    if frame is None:
        info["note"] = "没有画面"
        return info, None
    height, width = frame.shape[:2]
    info["shape"] = [int(height), int(width)]
    info["native_sbs"] = looks_side_by_side(frame)
    view, native_right = split_stereo(frame)
    left, right = pair_from_shift(view if view is not None else frame, shift_px)
    if right is None:
        info["note"] = "画面太窄，做不了平移视差"
        return info, None
    disparity, preview, _small = stereo_map(left, right)
    if disparity is None:
        info["note"] = "OpenCV SGBM 不可用"
        return info, preview
    try:
        import numpy as np
    except Exception:
        return info, preview
    valid = disparity[disparity > 0.5]
    if valid.size < 40:
        info["note"] = "有效视差太少（墙面太糊或纹理不够）"
        return info, preview
    median = float(np.median(valid))
    info["disparity_median"] = round(median, 2)
    fx = focal_px(left.shape[1], fov_deg=fov_deg)
    depth = disparity_to_depth_m(median, fx=fx, baseline_m=baseline_m)
    info["depth_m_if_baseline_6cm"] = None if depth is None else round(depth, 3)
    info["pipeline_ok"] = abs(median - float(shift_px)) <= max(5.0, 0.4 * float(shift_px))
    info["ok"] = True
    if info["native_sbs"] and native_right is not None:
        info["note"] = "机载是左右拼图，迎宾可以走真双目。下面的视差是平移自检。"
    else:
        info["note"] = (
            "机载 GetImageSample 仍是单路 JPEG，没有真左右目。"
            "右上角色块是把同一帧平移后跑 SGBM，只验收算法，不用于安全距离。"
        )
    return info, preview


def largest_box(boxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float] | None:
    if not boxes:
        return None
    return max(boxes, key=lambda box: max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1]))


def stereo_map(left, right, *, max_width: int = 320):
    """返回 (视差图 float32, 用于预览的着色图, 缩放后的左图)。匹配失败则视差为 None。"""
    try:
        import cv2
        import numpy as np
    except Exception:
        return None, None, left
    if left is None or right is None:
        return None, None, left
    h, w = left.shape[:2]
    if w > max_width:
        scale = max_width / w
        size = (max_width, max(1, int(h * scale)))
        left_s = cv2.resize(left, size)
        right_s = cv2.resize(right, size)
    else:
        left_s, right_s, scale = left, right, 1.0
    gray_l = cv2.cvtColor(left_s, cv2.COLOR_BGR2GRAY) if left_s.ndim == 3 else left_s
    gray_r = cv2.cvtColor(right_s, cv2.COLOR_BGR2GRAY) if right_s.ndim == 3 else right_s
    num = 96
    matcher = cv2.StereoSGBM_create(
        minDisparity=0,
        numDisparities=num,
        blockSize=5,
        P1=8 * 3 * 25,
        P2=32 * 3 * 25,
        uniquenessRatio=8,
        speckleWindowSize=50,
        speckleRange=2,
        disp12MaxDiff=1,
        mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY,
    )
    raw = matcher.compute(gray_l, gray_r).astype(np.float32) / 16.0
    raw[raw < 0.5] = 0.0
    # 视差按缩放还原到原分辨率像素。
    if scale != 1.0:
        raw = raw / scale
    color = _colorize_disparity(raw)
    return raw, color, left_s


def median_depth_in_box(
    disparity,
    box: tuple[float, float, float, float],
    *,
    fx: float,
    baseline_m: float = DEFAULT_BASELINE_M,
) -> float | None:
    try:
        import numpy as np
    except Exception:
        return None
    if disparity is None or disparity.size == 0:
        return None
    h, w = disparity.shape[:2]
    x1 = max(0, int(box[0] * w))
    y1 = max(0, int(box[1] * h))
    x2 = min(w, int(box[2] * w))
    y2 = min(h, int(box[3] * h))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    patch = disparity[y1:y2, x1:x2]
    valid = patch[patch > 0.5]
    if valid.size < 20:
        return None
    depth = disparity_to_depth_m(float(np.median(valid)), fx=fx, baseline_m=baseline_m)
    if depth is None or depth < 0.05 or depth > 8.0:
        return None
    return depth


def estimate_distance(
    frame,
    boxes: list[tuple[float, float, float, float]],
    *,
    baseline_m: float = DEFAULT_BASELINE_M,
    landmarks=None,
    fov_deg: float | None = None,
    preview_shift_px: int = 0,
) -> tuple[DistanceEstimate, object]:
    """返回距离估计，以及可选的深度预览图。真拼图才用视差当距离；平移色块只供预览。"""
    left, right = split_stereo(frame)
    native = right is not None
    view = left if left is not None else frame
    box = pose_span_box(landmarks) if landmarks else None
    box = box or largest_box(boxes)
    preview = None
    disparity = None
    if view is None:
        return DistanceEstimate(None, "none"), None
    height, width = view.shape[:2]
    fov = float(fov_deg if fov_deg is not None else LAPTOP_HFOV_DEG)
    fx = focal_px(width, fov_deg=fov)
    if native:
        disparity, preview, _small = stereo_map(left, right)
    elif preview_shift_px > 0:
        shifted_l, shifted_r = pair_from_shift(view, preview_shift_px)
        if shifted_r is not None:
            disparity, preview, _small = stereo_map(shifted_l, shifted_r)
    pose_m = None
    pose_src = ""
    if landmarks:
        pose_m, pose_src = pose_distance_m(landmarks, width, height, fov_deg=fov)
    if native and box is not None and disparity is not None:
        meters = median_depth_in_box(disparity, box, fx=fx, baseline_m=baseline_m)
        if meters is not None:
            return DistanceEstimate(meters, "stereo", box, True), preview
    if pose_m is not None:
        return DistanceEstimate(pose_m, pose_src, box, native), preview
    if native and box is not None:
        meters = bbox_distance_m(box, height, person_height_m=TORSO_LENGTH_M, fy=fx, frame_width=width)
        return DistanceEstimate(meters, "bbox-torso", box, True), preview
    if native:
        return DistanceEstimate(None, "stereo-empty", None, True), preview
    if box is None:
        return DistanceEstimate(None, "no-person"), preview
    metric = TORSO_LENGTH_M if landmarks else PERSON_HEIGHT_M
    source = "bbox-torso" if landmarks else "bbox"
    meters = bbox_distance_m(box, height, person_height_m=metric, fy=fx, frame_width=width)
    return DistanceEstimate(meters, source, box, False), preview


def classify_zone(meters: float | None) -> str:
    if meters is None:
        return "unknown"
    if meters < DANGER_M:
        return "danger"
    if meters < CAUTION_M:
        return "caution"
    if meters <= GREET_MAX_M:
        return "greet"
    return "far"


def _colorize_disparity(disparity):
    """固定量程上色。0 视差（右边缘搜不到、墙面没纹理）涂灰，不再被拉成整片紫或红。"""
    try:
        import cv2
        import numpy as np
    except Exception:
        return None
    valid = disparity > 0.5
    scaled = np.clip(disparity, 0, 48) * (255.0 / 48.0)
    vis = np.zeros(disparity.shape, dtype=np.uint8)
    vis[valid] = scaled[valid].astype(np.uint8)
    color = cv2.applyColorMap(vis, cv2.COLORMAP_TURBO)
    color[~valid] = (48, 48, 48)
    return color


def overlay_proximity(frame, estimate: DistanceEstimate, zone: str, label: str, depth_preview=None):
    try:
        import cv2
    except Exception:
        return frame
    if frame is None:
        return frame
    painted = frame.copy()
    if depth_preview is not None:
        dh, dw = depth_preview.shape[:2]
        h, w = painted.shape[:2]
        small_w = max(80, w // 3)
        small_h = max(1, int(dh * small_w / max(dw, 1)))
        thumb = cv2.resize(depth_preview, (small_w, small_h))
        painted[8 : 8 + small_h, w - 8 - small_w : w - 8] = thumb
    if estimate.box:
        h, w = painted.shape[:2]
        x1, y1, x2, y2 = (
            int(estimate.box[0] * w),
            int(estimate.box[1] * h),
            int(estimate.box[2] * w),
            int(estimate.box[3] * h),
        )
        color = {
            "danger": (40, 40, 220),
            "caution": (40, 160, 255),
            "greet": (40, 200, 90),
            "far": (180, 180, 180),
        }.get(zone, (160, 160, 160))
        cv2.rectangle(painted, (x1, y1), (x2, y2), color, 3)
    dist = "—" if estimate.meters is None else f"{estimate.meters:.2f} m"
    cv2.rectangle(painted, (8, 8), (min(painted.shape[1] - 8, 520), 78), (20, 12, 40), -1)
    cv2.putText(painted, f"{dist}  {zone}  {estimate.source}", (16, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 240, 220), 2)
    cv2.putText(painted, label[:48], (16, 66), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 200), 1)
    return painted
