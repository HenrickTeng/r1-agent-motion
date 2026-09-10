"""分阶段单功能探测：不连真机、不开课堂网页，只把识别结果打到终端。"""

from __future__ import annotations

import json
import time

from r1_studio.gestures import GesturePilot, classify_hand
from r1_studio.teleop import keys_to_twist


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def probe_gestures(*, camera: int | None, r1_camera: bool, interface: str, window: bool) -> int:
    import cv2

    from r1_studio.camera import open_camera
    from r1_studio.hands import HandTracker, overlay_hands

    source = open_camera(
        camera=0 if camera is None and not r1_camera else camera,
        r1_camera=r1_camera,
        interface=interface,
        synthetic=False,
    )
    source.start()
    last = None
    last_beat = 0.0
    if r1_camera:
        from r1_studio.body import BodyPilot, PoseTracker, overlay_pose

        tracker = PoseTracker()
        body = BodyPilot()
        _print({
            "probe": "gestures",
            "strategy": "pose",
            "hint": "机载用跟臂同款 Pose：先侧平举锁定。只打印，不驱动。Q 退出。",
            "camera": source.label,
        })
    else:
        tracker = HandTracker(num_hands=2)
        mirrored = True
        pilot = GesturePilot(mirrored=mirrored, face_to_face=True)
        body = None
        _print({
            "probe": "gestures",
            "strategy": "hands",
            "face_to_face": True,
            "mirrored": True,
            "hint": "笔记本手部关键点。面对面：你的左=机器人右移。只打印，不驱动。Q 退出。",
            "camera": source.label,
        })
    try:
        while True:
            frame, _jpeg = source.snapshot()
            if frame is None:
                time.sleep(0.03)
                continue
            if r1_camera:
                landmarks = tracker.detect_bgr(frame)
                command = body.step(landmarks, time.time())
                poses = [command.pose] if command.pose and command.pose != "none" else []
                payload = {
                    "t": round(time.time(), 2),
                    "strategy": "pose",
                    "poses": poses,
                    "kind": command.kind,
                    "label": command.label,
                    "vx": round(command.vx, 3),
                    "vy": round(command.vy, 3),
                    "omega": round(command.omega, 3),
                    "operator": body.status,
                }
                if window:
                    shown = overlay_pose(frame.copy(), landmarks, command.label, body.box)
                    cv2.imshow("R1 gesture probe", shown)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("q"), 27):
                        break
            else:
                hands = tracker.detect_bgr(frame)
                command = pilot.step(hands, time.time())
                poses = [classify_hand(hand) for hand in hands]
                payload = {
                    "t": round(time.time(), 2),
                    "strategy": "hands",
                    "hands": len(hands),
                    "poses": poses,
                    "kind": command.kind,
                    "label": command.label,
                    "vx": round(command.vx, 3),
                    "vy": round(command.vy, 3),
                    "omega": round(command.omega, 3),
                    "operator": "off",
                }
                if window:
                    shown = overlay_hands(frame.copy(), hands, command.label)
                    cv2.imshow("R1 gesture probe", shown)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("q"), 27):
                        break
            signature = (
                tuple(poses),
                command.kind,
                round(command.vx, 1),
                round(command.vy, 1),
                round(command.omega, 1),
                command.label,
            )
            now = time.time()
            if signature != last or now - last_beat >= 1.0:
                print(json.dumps(payload, ensure_ascii=False), flush=True)
                last = signature
                last_beat = now
            if not window:
                time.sleep(0.03)
    except KeyboardInterrupt:
        print('{"probe":"gestures","event":"interrupt"}', flush=True)
    finally:
        source.close()
        if window:
            cv2.destroyAllWindows()
    return 0


def probe_vision(*, camera: int | None, r1_camera: bool, interface: str, window: bool) -> int:
    import cv2

    from r1_studio.camera import open_camera
    from r1_studio.vision import summarize_detections

    source = open_camera(
        camera=0 if camera is None and not r1_camera else camera,
        r1_camera=r1_camera,
        interface=interface,
        synthetic=False,
    )
    source.start()
    time.sleep(0.4)
    from r1_studio.vision import MediaPipeObjectDetector

    detector = MediaPipeObjectDetector()
    _print({
        "probe": "vision",
        "hint": "把物品放镜头中间。每秒打印一帧检测，不说话、不动机器人。Q 退出。",
        "camera": source.label,
    })
    try:
        while True:
            frame, _jpeg = source.snapshot()
            if frame is None:
                time.sleep(0.05)
                continue
            items = detector.detect_bgr(frame)
            payload = {
                "t": round(time.time(), 2),
                "items": [
                    {
                        "label": item.label,
                        "zh": item.title_zh,
                        "category": item.category,
                        "score": round(item.score, 3),
                    }
                    for item in items
                ],
                "reply": summarize_detections(items),
            }
            _print(payload)
            if window:
                cv2.imshow("R1 vision probe", frame)
                key = cv2.waitKey(800) & 0xFF
                if key in (ord("q"), 27):
                    break
            else:
                time.sleep(0.8)
    except KeyboardInterrupt:
        print('{"probe":"vision","event":"interrupt"}', flush=True)
    finally:
        source.close()
        if window:
            cv2.destroyAllWindows()
    return 0


def probe_keys() -> int:
    try:
        import cv2
        import numpy as np
    except ImportError as error:
        raise SystemExit("键盘探测需要 opencv-python") from error

    held: set[str] = set()
    canvas = np.zeros((240, 520, 3), np.uint8)
    _print({"probe": "keys", "hint": "焦点在窗口：WASD/QE，空格清空。只打印速度，不连机器人。"})
    mapping = {
        ord("w"): "w",
        ord("a"): "a",
        ord("s"): "s",
        ord("d"): "d",
        ord("q"): "q",
        ord("e"): "e",
    }
    last = ""
    while True:
        canvas[:] = (40, 28, 72)
        vx, vy, omega = keys_to_twist(sorted(held))
        text = f"keys={sorted(held)}  vx={vx:.2f} vy={vy:.2f} om={omega:.2f}"
        cv2.putText(canvas, text, (16, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 240, 240), 1)
        cv2.putText(canvas, "WASD QE | SPACE clear | ESC quit", (16, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.imshow("R1 key probe", canvas)
        key = cv2.waitKey(80) & 0xFF
        if key in (27,):
            break
        if key == 32:
            held.clear()
        elif key in mapping:
            held.add(mapping[key])
        line = json.dumps({"keys": sorted(held), "vx": vx, "vy": vy, "omega": omega}, ensure_ascii=False)
        if line != last:
            print(line, flush=True)
            last = line
    cv2.destroyAllWindows()
    return 0


def probe_llm() -> int:
    """只测 DeepSeek 文本连通性，不打印密钥。"""
    from urllib import error, request

    from r1_agent.planner import (
        chat_body,
        extract_message_text,
        load_deepseek_key,
        load_deepseek_model,
        load_deepseek_url,
    )

    key = load_deepseek_key()
    url = load_deepseek_url()
    model = load_deepseek_model()
    _print({
        "probe": "llm",
        "has_key": bool(key),
        "key_len": len(key),
        "key_prefix": (key[:3] + "…") if len(key) >= 3 else "",
        "url": url,
        "model": model,
    })
    if not key:
        _print({"ok": False, "error": "没有 DEEPSEEK_API_KEY，也没有 deepseek_key.txt"})
        return 1
    if "公司给你的" in key or key.strip() in {"key", "your-key"}:
        _print({"ok": False, "error": "当前密钥像是文档里的占位符，请换成公司发给你的 sk- 真实 Key"})
        return 1
    body = chat_body(
        model,
        [{"role": "user", "content": "只回复两个字：连通"}],
        max_tokens=64,
        temperature=0,
    )
    req = request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=20) as response:
            envelope = json.loads(response.read())
        message = envelope["choices"][0]["message"]
        text = extract_message_text(message)
        finish = envelope["choices"][0].get("finish_reason")
        _print({
            "ok": bool(text),
            "reply": text,
            "finish_reason": finish,
            "has_reasoning": bool(message.get("reasoning_content")),
        })
        return 0 if text else 1
    except error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")[:400]
        _print({"ok": False, "http": err.code, "error": detail})
        return 1
    except Exception as err:
        _print({"ok": False, "error": str(err)})
        return 1
