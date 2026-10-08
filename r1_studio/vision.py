"""校园识别：看一眼 + 对话。优先公司 DeepSeek 多模态（默认 deepseek-flash / V4.1），
本地检测器作后备。有校园背景就按平面指路；没有具体馆藏就只说类型和寻找方向。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib import error, request

from r1_agent.catalog import ROOT
from r1_agent.planner import (
    chat_body,
    extract_message_text,
    load_deepseek_key,
    load_deepseek_model,
    load_deepseek_url,
    normalize_chat_url,
)

VISION_PHRASES = (
    "进入物体识别",
    "进入物品识别",
    "物体识别模式",
    "物品识别模式",
    "失物识别",
    "失物招领",
    "识别一下",
    "这是什么",
    "看看这是什么",
    "帮我认一下",
    "这本书该放",
    "该书放",
    "该放在哪",
    "该放哪里",
    "该放那儿",
    "该放那里",
    "放哪儿",
    "去哪找",
    "去哪儿找",
    "这是什么书",
    "帮我看看",
    "看一下这个",
    "校园导览",
)

CAMPUS_DIR = ROOT / "scenes" / "campus"

COCO_TO_LOST = {
    "bottle": ("水瓶", "水瓶或饮料瓶"),
    "wine glass": ("杯子", "杯子"),
    "cup": ("杯子", "杯子"),
    "bowl": ("餐具", "碗或餐盒"),
    "backpack": ("书包", "书包"),
    "handbag": ("包", "手提包"),
    "suitcase": ("箱子", "行李箱或大包"),
    "umbrella": ("雨伞", "雨伞"),
    "book": ("书本", "书本或作业本"),
    "cell phone": ("手机", "手机"),
    "remote": ("遥控器", "遥控器"),
    "laptop": ("电脑", "笔记本电脑"),
    "keyboard": ("文具", "键盘"),
    "mouse": ("文具", "鼠标"),
    "scissors": ("文具", "剪刀"),
    "clock": ("其他", "时钟或手表"),
    "tie": ("衣物", "领带或衣物"),
    "teddy bear": ("玩具", "毛绒玩具"),
    "sports ball": ("其他", "球类"),
    "bottle cap": ("水瓶", "瓶盖"),
}


@dataclass(frozen=True)
class Detection:
    label: str
    score: float
    box: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)

    @property
    def category(self) -> str:
        mapped = COCO_TO_LOST.get(self.label.lower())
        return mapped[0] if mapped else "其他"

    @property
    def title_zh(self) -> str:
        mapped = COCO_TO_LOST.get(self.label.lower())
        return mapped[1] if mapped else self.label


def is_vision_intent(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    return any(phrase in compact for phrase in VISION_PHRASES)


def load_campus_text(name: str = "context.txt") -> str:
    path = CAMPUS_DIR / name
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def campus_system_prompt(campus_context: str) -> str:
    rules = (
        "你是校园里的 Unitree R1 课堂助手，能看眼前物品，回答失物招领、问路、"
        "「这本书该放哪」这类有逻辑的校园问题。"
        "用两三句适合中学生的中文。不要提 API、模型或检测分数。"
        "规则：校园背景里写明的地点、楼层、房间、书架必须遵守；"
        "背景没写的地点，禁止编造具体楼层、房间号、架号。"
        "没有馆藏平面时：先说物品类型（如语文课本、水瓶），再给合理寻找方向"
        "（教学楼、班级图书角、失物招领处、问老师），并说明这是根据常识的建议。"
        "有图书馆平面时：书按学科放到对应楼层区域；水杯书包雨伞等非图书交还书处失物柜。"
    )
    context = (campus_context or "").strip()
    if context:
        return rules + "\n\n【校园背景】\n" + context
    return rules + "\n\n【校园背景】未提供具体场所平面。不要编造楼层房间号。"


def campus_user_text(question: str, detections: list[Detection]) -> str:
    asked = (question or "").strip() or "请看眼前画面：这是什么？如果是校园物品，说明类型，以及可以怎么处理或去哪。"
    labels = "、".join(f"{item.title_zh}({item.category})" for item in detections[:6]) or "本地检测器没有给出标签"
    return f"同学问：{asked}\n本地检测参考（可与画面不一致）：{labels}"


def summarize_detections(items: list[Detection], *, min_score: float = 0.35) -> str:
    kept = [item for item in items if item.score >= min_score]
    if not kept:
        return "这一帧里我没有认出常见的校园失物。请把物品放在镜头中间，再试一次。"
    kept.sort(key=lambda item: item.score, reverse=True)
    top = kept[0]
    extra = [item.title_zh for item in kept[1:3] if item.category != top.category]
    line = f"我看到最可能是{top.title_zh}，属于{top.category}类失物。"
    if extra:
        line += "另外还看到" + "、".join(extra) + "。"
    line += "请到失物招领处登记，不要把别人的东西带走。"
    return line


def _chat_complete(messages: list[dict], *, api_key: str, api_url: str, model: str, timeout_s: float = 25) -> str:
    body = chat_body(model, messages, temperature=0.2, max_tokens=280)
    req = request.Request(
        normalize_chat_url(api_url),
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_s) as response:
        envelope = json.loads(response.read())
    return extract_message_text(envelope["choices"][0]["message"])


def ask_campus(
    *,
    question: str,
    detections: list[Detection],
    jpeg: bytes = b"",
    campus_context: str = "",
    history: list[dict] | None = None,
    api_key: str = "",
    api_url: str = "",
    model: str = "",
) -> str:
    """看图+校园背景对话。多模态失败则退回纯文本；再失败用本地检测草稿。"""
    key = (api_key or load_deepseek_key() or os.getenv("VLM_API_KEY") or "").strip()
    url = api_url or os.getenv("VLM_API_URL") or load_deepseek_url()
    name = (model or os.getenv("VLM_MODEL") or load_deepseek_model()).strip()
    draft = summarize_detections(detections)
    if not key:
        return draft
    system = campus_system_prompt(campus_context)
    user = campus_user_text(question, detections)
    prior = []
    for turn in (history or [])[-8:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            prior.append({"role": role, "content": content.strip()})
    text_messages = [{"role": "system", "content": system}, *prior, {"role": "user", "content": user}]
    if jpeg:
        import base64

        b64 = base64.b64encode(jpeg).decode("ascii")
        vision_messages = [
            {"role": "system", "content": system},
            *prior,
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            },
        ]
        try:
            return _chat_complete(vision_messages, api_key=key, api_url=url, model=name) or draft
        except (error.URLError, TimeoutError, KeyError, json.JSONDecodeError, IndexError, TypeError, OSError):
            pass
    try:
        return _chat_complete(text_messages, api_key=key, api_url=url, model=name) or draft
    except (error.URLError, TimeoutError, KeyError, json.JSONDecodeError, IndexError, TypeError, OSError):
        return draft


def enrich_reply_deepseek(labels: list[str], draft: str) -> str:
    fake = [Detection(label=name, score=1.0) for name in labels]
    return ask_campus(question="请用课堂用语说检测结果", detections=fake, jpeg=b"", campus_context="")


def describe_frame_vlm(jpeg: bytes) -> str:
    return ask_campus(question="用一句中文说出画面里最可能的校园物品", detections=[], jpeg=jpeg)


class MediaPipeObjectDetector:
    def __init__(self, model_path: Path | None = None) -> None:
        import urllib.request

        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import ObjectDetector, ObjectDetectorOptions, RunningMode
        import mediapipe as mp

        path = model_path or (ROOT / "r1_studio" / "assets" / "efficientdet_lite0.tflite")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.stat().st_size < 100_000:
            url = (
                "https://storage.googleapis.com/mediapipe-models/object_detector/"
                "efficientdet_lite0/float16/1/efficientdet_lite0.tflite"
            )
            urllib.request.urlretrieve(url, path)
        options = ObjectDetectorOptions(
            base_options=BaseOptions(model_asset_path=str(path)),
            running_mode=RunningMode.IMAGE,
            max_results=8,
            score_threshold=0.28,
        )
        self._detector = ObjectDetector.create_from_options(options)
        self._mp = mp

    def detect_bgr(self, frame) -> list[Detection]:
        import cv2

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._detector.detect(image)
        h, w = frame.shape[:2]
        items: list[Detection] = []
        for det in result.detections or []:
            cat = det.categories[0]
            bbox = det.bounding_box
            items.append(
                Detection(
                    label=(cat.category_name or "object").replace("_", " "),
                    score=float(cat.score or 0),
                    box=(
                        bbox.origin_x / w,
                        bbox.origin_y / h,
                        (bbox.origin_x + bbox.width) / w,
                        (bbox.origin_y + bbox.height) / h,
                    ),
                )
            )
        return items


def person_boxes(items: list[Detection], *, min_score: float = 0.25) -> list[tuple[float, float, float, float]]:
    return [
        item.box
        for item in items
        if item.label.lower() == "person" and item.score >= min_score
    ]


def detect_frame(frame) -> list[Detection]:
    try:
        return MediaPipeObjectDetector().detect_bgr(frame)
    except Exception:
        return []
