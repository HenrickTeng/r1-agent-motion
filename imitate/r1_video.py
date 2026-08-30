"""R1 头部图传：复用 Go2 VideoClient.GetImageSample（JPEG）。不发 arm_sdk。"""

from __future__ import annotations

import cv2
import numpy as np

from r1_agent.dds_setup import prepare_cyclonedds
from r1_agent.interface import resolve_interface


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
        code, data = self._client.GetImageSample()
        if code != 0 or not data:
            raise RuntimeError(f"R1 GetImageSample 失败 code={code} 网卡={nic}")
        self._opened = True
        self._last = None
        print(f"R1 图传已通（Go2 VideoClient），网卡 {nic}，首帧 {len(data)} 字节。")
        ok, frame = self._decode(data)
        if ok:
            self._last = frame

    def _decode(self, data) -> tuple[bool, object]:
        image = cv2.imdecode(np.frombuffer(bytes(data), dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return False, None
        return True, image

    def isOpened(self) -> bool:
        return self._opened

    def set(self, *_args) -> None:
        return None

    def read(self):
        code, data = self._client.GetImageSample()
        if code != 0 or not data:
            if self._last is not None:
                return True, self._last
            return False, None
        ok, image = self._decode(data)
        if not ok:
            if self._last is not None:
                return True, self._last
            return False, None
        self._last = image
        return True, image

    def release(self) -> None:
        self._opened = False
