from __future__ import annotations

import argparse
import threading
from pathlib import Path

from r1_agent.catalog import ROOT
from r1_studio.camera import open_camera
from r1_studio.server import serve
from r1_studio.session import StudioSession


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R1 教师电脑本地课堂控制台")
    parser.add_argument("--hardware", action="store_true")
    parser.add_argument("--interface", default="auto")
    parser.add_argument("--camera", type=int, default=None, help="笔记本摄像头编号，如 0；不写则进网页再选")
    parser.add_argument("--r1-camera", action="store_true", help="启动时直接用机载；不写则进网页再选")
    parser.add_argument("--synthetic-camera", action="store_true", help="无摄像头时用色块画面调试 UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--scene", default="")
    parser.add_argument(
        "--probe",
        choices=["gestures", "vision", "keys", "llm"],
        default="",
        help="分阶段单功能探测：只打印识别结果，不启动网页、不驱动机器人",
    )
    parser.add_argument("--window", action="store_true", help="probe 时额外开预览窗")
    parser.add_argument("--preview", action="store_true", help="电脑屏幕打开摄像头识别预览窗")
    parser.add_argument("--no-preview", action="store_true", help="不要预览窗")
    parser.add_argument(
        "--groups",
        default=str(ROOT / "programs" / "custom_groups.json"),
        help="自定义动作组保存路径",
    )
    args = parser.parse_args(argv)
    if args.camera is not None and args.r1_camera:
        parser.error("电脑摄像头和 R1 机载摄像头只能选一个")
    if args.probe == "gestures":
        from r1_studio.probe import probe_gestures

        return probe_gestures(
            camera=args.camera,
            r1_camera=args.r1_camera,
            interface=args.interface,
            window=args.window,
        )
    if args.probe == "vision":
        from r1_studio.probe import probe_vision

        return probe_vision(
            camera=args.camera,
            r1_camera=args.r1_camera,
            interface=args.interface,
            window=args.window,
        )
    if args.probe == "keys":
        from r1_studio.probe import probe_keys

        return probe_keys()
    if args.probe == "llm":
        from r1_studio.probe import probe_llm

        return probe_llm()
    synthetic = args.synthetic_camera or (args.camera is None and not args.r1_camera)
    preview = bool(args.preview) and not args.no_preview
    if args.r1_camera:
        cam_source = "r1"
    elif args.synthetic_camera or (args.camera is None and not args.r1_camera):
        cam_source = "synthetic"
    else:
        cam_source = "laptop"
    camera = open_camera(
        camera=args.camera,
        r1_camera=args.r1_camera,
        interface=args.interface,
        synthetic=synthetic,
    )
    if cam_source == "synthetic":
        print("尚未打开摄像头：浏览器画面下方点「笔记本摄像头」或「R1 机载摄像头」", flush=True)
    robot = None
    if args.hardware:
        from r1_agent.hardware import DeferredHardware, R1Hardware

        backend = DeferredHardware()
        print('{"mode":"hardware","status":"connecting"}', flush=True)
    else:
        from r1_agent.executor import SimulatedBackend

        backend = SimulatedBackend()
        print('{"mode":"simulate"}', flush=True)
    session = StudioSession(
        backend=backend,
        camera=camera,
        hardware=args.hardware,
        listen_robot=robot,
        groups_path=Path(args.groups),
        scene=args.scene,
        mirrored_camera=not args.r1_camera,
        face_to_face=True,
        preview_window=preview,
        interface=args.interface,
        camera_source=cam_source,
        laptop_index=0 if args.camera is None else int(args.camera),
    )
    if args.hardware:
        session.last_reply = "网页已打开。机器人正在后台连接，终端出现「机器人已就绪」后再点开始。"

        def connect_robot() -> None:
            try:
                from r1_agent.dds_robot import DdsRobot

                bound = DdsRobot(args.interface)
                print(json_interface(bound._interface), flush=True)
                session.last_reply = "DDS 已通，正在初始化行走和语音客户端…"
                bound._ensure_loco()
                bound._ensure_tts()
                backend.attach(R1Hardware(args.interface, robot=bound))
                session.listen_robot = bound
                session.last_reply = "机器人已就绪。可以点「开始」控制。"
                session.last_error = ""
                print("机器人已就绪", flush=True)
            except Exception as error:
                backend.fail(str(error))
                session.last_error = str(error)
                print(f"连接机器人失败：{error}", flush=True)

        threading.Thread(target=connect_robot, daemon=True).start()
    if preview:
        print("电脑预览窗：R1 laptop camera preview。浏览器 http://127.0.0.1:%s" % args.port, flush=True)
    serve(session, args.host, args.port)
    return 0


def json_interface(name: str) -> str:
    import json

    return json.dumps({"interface": name}, ensure_ascii=False)


if __name__ == "__main__":
    raise SystemExit(main())
