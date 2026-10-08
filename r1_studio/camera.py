from __future__ import annotations

import threading
import time
from typing import Any

PLACEHOLDER_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c"
    b"\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c"
    b"\x1c $.' \"#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00"
    b"\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\t\xff\xc4\x00\x14\x10\x01"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\x7f\x3f\xff\xd9"
)


class FrameSource:
    def __init__(self, cap: Any | None, *, mirror: bool = False) -> None:
        self._cap = cap
        self._lock = threading.Lock()
        self.frame = None
        self.jpeg = PLACEHOLDER_JPEG
        self.label = "无摄像头（仿真画面）"
        self.mirror = mirror
        self.overlay_preview = False
        self._raw_jpeg = PLACEHOLDER_JPEG
        self._overlay_jpeg = b""
        self._overlay_t = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass

    def _loop(self) -> None:
        while not self._stop.is_set():
            frame = self._read()
            jpeg = _encode(shrink_frame(frame)) if frame is not None else PLACEHOLDER_JPEG
            with self._lock:
                if frame is not None:
                    self.frame = frame
                self._raw_jpeg = jpeg
                self.jpeg = self._pick_jpeg()
            time.sleep(0.04)

    def _read(self):
        if self._cap is None:
            return _synthetic_frame()
        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None
        if self.mirror:
            import cv2

            return cv2.flip(frame, 1)
        return frame

    def snapshot(self):
        with self._lock:
            return self.frame, self.jpeg

    def set_preview_jpeg(self, jpeg: bytes) -> None:
        with self._lock:
            self._overlay_jpeg = jpeg
            self._overlay_t = time.time()
            self.jpeg = self._pick_jpeg()

    def set_overlay_preview(self, on: bool) -> None:
        with self._lock:
            self.overlay_preview = bool(on)
            self.jpeg = self._pick_jpeg()

    def _pick_jpeg(self) -> bytes:
        fresh = self.overlay_preview and self._overlay_jpeg and (time.time() - self._overlay_t) < 0.4
        if fresh:
            return self._overlay_jpeg
        return self._raw_jpeg or PLACEHOLDER_JPEG


def _synthetic_frame():
    try:
        import numpy as np
    except Exception:
        return None
    t = int(time.time() * 8) % 80
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    frame[:, :] = (48, 32, 96)
    frame[80:280, 180:460] = (96 + t, 64, 140)
    return frame


def shrink_frame(frame, max_width: int = 640):
    if frame is None:
        return None
    height, width = frame.shape[:2]
    if width <= max_width:
        return frame
    import cv2

    return cv2.resize(frame, (max_width, max(1, int(height * max_width / width))))


def _encode(frame) -> bytes:
    try:
        import cv2

        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        if ok:
            return bytes(buf)
    except Exception:
        pass
    return PLACEHOLDER_JPEG


def wide_angle_crop(frame, *, cover: float = 0.50):
    """R1 超广角：只取画面中下部，把人放大再给 MediaPipe。"""
    if frame is None:
        return None
    height, width = frame.shape[:2]
    if width < 80 or height < 80:
        return frame
    crop_w = max(80, int(width * cover))
    crop_h = max(80, int(height * 0.58))
    x0 = (width - crop_w) // 2
    y0 = min(height - crop_h, int((height - crop_h) * 0.62))
    return frame[y0 : y0 + crop_h, x0 : x0 + crop_w]


def body_crop(frame, *, cover: float = 0.72):
    """机载全身 Pose：比抠手裁得更宽，避免侧平举把手臂切掉。"""
    if frame is None:
        return None
    height, width = frame.shape[:2]
    if width < 80 or height < 80:
        return frame
    crop_w = max(80, int(width * cover))
    crop_h = max(80, int(height * 0.80))
    x0 = (width - crop_w) // 2
    y0 = min(height - crop_h, int((height - crop_h) * 0.42))
    return frame[y0 : y0 + crop_h, x0 : x0 + crop_w]


def open_camera(*, camera: int | None, r1_camera: bool, interface: str, synthetic: bool):
    if synthetic:
        return FrameSource(None)
    if r1_camera:
        from imitate.r1_video import R1VideoCapture

        cap = R1VideoCapture(interface)
        source = FrameSource(cap, mirror=False)
        source.label = "R1 机载摄像头（全身 Pose，不裁切）"
        return source
    if camera is None:
        return FrameSource(None)
    import cv2

    cap = cv2.VideoCapture(int(camera))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    if not cap.isOpened():
        raise RuntimeError(f"打不开摄像头 {camera}")
    source = FrameSource(cap, mirror=True)
    source.label = f"电脑摄像头 {camera}（镜像）"
    return source
