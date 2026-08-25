"""Parse R1 ASR output, including firmware that never sets is_final=true."""

import json
import string


PUNCTUATION_ONLY = set(string.punctuation + "，。！？、；：‘’“”（）《》…")


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
        if normalized and not all(character in PUNCTUATION_ONLY for character in normalized) and "<|nospeech|>" not in normalized and isinstance(confidence, (int, float)) and confidence >= minimum_confidence:
            candidates.append(message)
    if not candidates:
        raise ValueError("ASR output contains no acceptable transcript")
    final = [candidate for candidate in candidates if candidate.get("is_final") is True]
    return max(final, key=lambda item: item.get("confidence", 0)) if final else candidates[-1]
