"""Offline PC microphone recognition for the classroom DIY agent."""

from __future__ import annotations

from array import array
import json
import math
from pathlib import Path
import subprocess


SAMPLE_RATE = 16000
COMMAND_GRAMMAR = [
    "向 前 走 一 步",
    "往 前 走 一 步",
    "前 进 一 步",
    "向 前 走",
    "往 前 走",
    "前 进",
    "向 左 转",
    "往 左 转",
    "向 左 转 一 下",
    "往 左 边 转 一 下",
    "朝 左 边 转",
    "向 右 转",
    "往 右 转",
    "向 右 转 一 下",
    "往 右 边 转 一 下",
    "朝 右 边 转",
    "左 转",
    "右 转",
    "向 后 走 一 步",
    "往 后 走 一 步",
    "向 后 走",
    "往 后 走",
    "后 退",
    "挥 右 手",
    "挥 一 下 右 手",
    "挥 左 手",
    "挥 一 下 左 手",
    "挥 挥 手",
    "举 右 手",
    "抬 起 右 手",
    "把 右 手 举 起 来",
    "举 左 手",
    "抬 起 左 手",
    "把 左 手 举 起 来",
    "右 手 平 举",
    "左 手 平 举",
    "张 开 双 臂",
    "展 开 双 臂",
    "双 手 向 前",
    "请 移 动 右 手 腕 关 节",
    "移 动 右 手 腕 关 节",
    "右 手 腕 关 节",
    "请 移 动 右 肩 关 节",
    "移 动 右 肩 关 节",
    "右 肩 关 节",
    "向 左 横 移",
    "向 右 横 移",
    "跳 舞",
    "趴 下",
    "躺 下",
    "下 蹲",
    "跑 步",
    "后 空 翻",
    "停 止",
    "取 消",
    "你 好",
    "介 绍 一 下",
    "请 介 绍 一 下 自 己",
    "[unk]",
]


def arecord_command(device: str, seconds: int) -> list[str]:
    if not 1 <= seconds <= 30:
        raise ValueError("record seconds must be between 1 and 30")
    return [
        "arecord",
        "-q",
        "-D",
        device,
        "-t",
        "raw",
        "-f",
        "S16_LE",
        "-r",
        str(SAMPLE_RATE),
        "-c",
        "1",
        "-d",
        str(seconds),
    ]


def transcript_from_result(payload: str) -> str:
    text = json.loads(payload).get("text", "")
    normalized = "".join(text.split()) if isinstance(text, str) else ""
    if not normalized or normalized == "[unk]":
        raise RuntimeError("电脑麦克风没有识别到有效指令")
    return normalized


def pcm_level(pcm: bytes) -> tuple[int, int]:
    samples = array("h")
    samples.frombytes(pcm)
    if not samples:
        return 0, 0
    peak = max(abs(sample) for sample in samples)
    rms = round(math.sqrt(sum(sample * sample for sample in samples) / len(samples)))
    return rms, peak


class PcMicRecognizer:
    def __init__(self, model_path: Path, device: str, seconds: int = 4) -> None:
        if not model_path.is_dir():
            raise RuntimeError(f"Vosk 中文模型不存在: {model_path}")
        try:
            from vosk import KaldiRecognizer, Model, SetLogLevel
        except ImportError as error:
            raise RuntimeError("未安装 Vosk，请运行 .venv/bin/pip install vosk") from error
        SetLogLevel(-1)
        self.model = Model(str(model_path))
        self.recognizer_type = KaldiRecognizer
        self.device = device
        self.seconds = seconds

    def listen(self) -> str:
        print(f"电脑麦克风开始录音，请在 {self.seconds} 秒内说话…", flush=True)
        completed = subprocess.run(
            arecord_command(self.device, self.seconds),
            capture_output=True,
            check=False,
            timeout=self.seconds + 5,
        )
        if completed.returncode:
            detail = completed.stderr.decode(errors="replace").strip()
            raise RuntimeError(detail or "电脑麦克风录音失败")
        rms, peak = pcm_level(completed.stdout)
        print(f"麦克风声量: RMS={rms} peak={peak}", flush=True)
        if peak < 300:
            raise RuntimeError("电脑麦克风录到的声音过小，请检查输入设备或靠近麦克风")
        recognizer = self.recognizer_type(
            self.model,
            SAMPLE_RATE,
            json.dumps(COMMAND_GRAMMAR, ensure_ascii=False),
        )
        recognizer.AcceptWaveform(completed.stdout)
        return transcript_from_result(recognizer.FinalResult())
