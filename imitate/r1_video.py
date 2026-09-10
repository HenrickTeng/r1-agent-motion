"""R1 头部图传：复用 Go2 VideoClient.GetImageSample（JPEG）。不发 arm_sdk。

偶发坏 JPEG（截断、EOI 前多字节）不要交给 OpenCV/MediaPipe，沿用上一帧。
"""

from __future__ import annotations

import os
import threading

import cv2
import numpy as np

_DECODE_STDERR_LOCK = threading.Lock()

from r1_agent.dds_setup import prepare_cyclonedds
from r1_agent.interface import resolve_interface

SOI = b"\xff\xd8"
EOI = b"\xff\xd9"


def clip_jpeg(data) -> bytes | None:
    """只留下 SOI…EOI。没有完整标记则视为坏帧。"""
    raw = bytes(data)
    start = raw.find(SOI)
    if start < 0:
        return None
    end = raw.find(EOI, start + 2)
    if end < 0:
        return None
    clipped = raw[start : end + 2]
    if len(clipped) < 128:
        return None
    return clipped


def decode_jpeg(data) -> object | None:
    clipped = clip_jpeg(data)
    if clipped is None:
        return None
    # libjpeg 仍可能对夹心脏数据打 stderr；坏帧用上一帧，不要把警告刷满终端。
    null = os.open(os.devnull, os.O_WRONLY)
    saved = os.dup(2)
    try:
        os.dup2(null, 2)
        image = cv2.imdecode(np.frombuffer(clipped, dtype=np.uint8), cv2.IMREAD_COLOR)
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        os.close(null)
    if image is None or getattr(image, "size", 0) <= 0:
        return None
    return image


class R1VideoCapture:
    def __init__(self, interface: str = "auto") -> None:
        prepare_cyclonedds()
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize
        from unitree_sdk2py.go2.video.video_client import VideoClient

        nic = resolve_interface(interface)
        ChannelFactoryInitialize(0, nic)
        self._client = VideoClient()
        self._client.SetTimeout(3.0)
        self._client.Init()
        self._nic = nic
        self._opened = True
        self._last = None
        self._skipped = 0
        code, data = self._client.GetImageSample()
        if code != 0 or not data:
            raise RuntimeError(f"R1 GetImageSample 失败 code={code} 网卡={nic}")
        frame = decode_jpeg(data)
        if frame is None:
            raise RuntimeError(f"R1 图传首帧 JPEG 损坏，网卡={nic}")
        self._last = frame
        print(f"R1 图传已通（Go2 VideoClient），网卡 {nic}，首帧 {len(bytes(data))} 字节。坏帧将跳过。")

    def isOpened(self) -> bool:
        return self._opened

    def set(self, *_args) -> None:
        return None

    def read(self):
        code, data = self._client.GetImageSample()
        if code != 0 or not data:
            return self._reuse()
        frame = decode_jpeg(data)
        if frame is None:
            self._skipped += 1
            if self._skipped % 30 == 1:
                print(f"R1 图传跳过坏 JPEG（已累计 {self._skipped} 帧，沿用上一帧）", flush=True)
            return self._reuse()
        self._last = frame
        return True, frame

    def _reuse(self):
        if self._last is not None:
            return True, self._last
        return False, None

    def release(self) -> None:
        self._opened = False
