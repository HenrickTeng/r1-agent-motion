from __future__ import annotations

import json
from pathlib import Path
import subprocess
import string

from r1_agent.catalog import ROOT

PUNCTUATION_ONLY = set(string.punctuation + "，。！？、；：‘’“”（）《》…")


def _usable_text(text: str) -> bool:
    compact = "".join(character for character in text if character not in PUNCTUATION_ONLY and not character.isspace())
    return sum(1 for character in compact if "\u4e00" <= character <= "\u9fff") >= 2


def select_transcript(output: str, *, minimum_confidence: float = 0.45) -> dict:
    candidates: list[dict] = []
    for line in output.splitlines():
        try:
            message = json.loads(line.strip())
        except (json.JSONDecodeError, TypeError):
            continue
        text = message.get("text")
        confidence = message.get("confidence", 1.0)
        normalized = text.strip() if isinstance(text, str) else ""
        if (
            normalized
            and _usable_text(normalized)
            and "<|nospeech|>" not in normalized
            and isinstance(confidence, (int, float))
            and confidence >= minimum_confidence
        ):
            candidates.append(message)
    if not candidates:
        raise ValueError("ASR output contains no acceptable transcript")
    final = [candidate for candidate in candidates if candidate.get("is_final") is True]
    return max(final, key=lambda item: item.get("confidence", 0)) if final else candidates[-1]


def listen_once(
    interface: str,
    *,
    binary: Path | None = None,
    timeout_s: int = 30,
    minimum_confidence: float = 0.45,
) -> str:
    path = binary or ROOT / "build/robot/r1_asr_listener"
    completed = subprocess.run(
        [str(path), interface, str(timeout_s)],
        text=True,
        capture_output=True,
        timeout=timeout_s + 5,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "R1 ASR failed")
    return select_transcript(completed.stdout, minimum_confidence=minimum_confidence)["text"]
