"""在调用 ChannelFactoryInitialize 之前装好 CycloneDDS。

官方 unitree_sdk2_python 的 XML 把 Tracing Verbosity 设成 config。
本机 0.10.2 的 libddsc 在打印配置位图时会触发 glibc fortify（buffer overflow）。
走跑模式读 lowstate / 发 arm_sdk 都不需要这份调试日志。
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SAFE_XML = """<?xml version="1.0" encoding="UTF-8" ?>
    <CycloneDDS>
        <Domain Id="any">
            <General>
                <Interfaces>
                    <NetworkInterface name="$__IF_NAME__$" priority="default" multicast="default"/>
                </Interfaces>
            </General>
        </Domain>
    </CycloneDDS>"""


def _cyclonedds_home() -> Path | None:
    env = os.environ.get("CYCLONEDDS_HOME")
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.extend(
        (
            _REPO.parent / "unitree_sdk2_python" / ".deps" / "cyclonedds",
            Path("/home/henrick/具身智能课程第一部分/unitree_sdk2_python/.deps/cyclonedds"),
        )
    )
    for home in candidates:
        if (home / "lib" / "libddsc.so.0").is_file():
            return home
    return None


def prepare_cyclonedds() -> None:
    home = _cyclonedds_home()
    if home is not None:
        import ctypes

        lib = home / "lib"
        os.environ.setdefault("CYCLONEDDS_HOME", str(home))
        os.environ["LD_LIBRARY_PATH"] = str(lib) + os.pathsep + os.environ.get("LD_LIBRARY_PATH", "")
        ctypes.CDLL(str(lib / "libddsc.so.0"), mode=ctypes.RTLD_GLOBAL)
    from unitree_sdk2py.core import channel_config

    channel_config.ChannelConfigHasInterface = _SAFE_XML
