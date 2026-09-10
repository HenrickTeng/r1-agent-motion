from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from r1_studio.session import StudioSession

STATIC = Path(__file__).resolve().parent / "static"


class StudioHandler(BaseHTTPRequestHandler):
    session: StudioSession

    def log_message(self, format: str, *args) -> None:
        if args and str(args[0]).startswith("GET /video"):
            return
        super().log_message(format, *args)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._file(STATIC / "index.html", "text/html; charset=utf-8")
        if path.startswith("/static/"):
            name = Path(path).name
            file = STATIC / name
            if file.is_file() and file.resolve().parent == STATIC.resolve():
                mime = "text/css" if file.suffix == ".css" else "text/javascript" if file.suffix == ".js" else "application/octet-stream"
                return self._file(file, mime)
            self.send_error(404)
            return
        if path == "/video.mjpg":
            return self._mjpeg()
        if path == "/api/state":
            return self._json(200, self.session.state())
        if path == "/api/catalog":
            return self._json(200, self.session.catalog_payload())
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        payload = self._read_json()
        try:
            if path == "/api/mode":
                self.session.set_mode(str(payload.get("mode") or "idle"))
                return self._json(200, self.session.state())
            if path == "/api/teleop":
                keys = payload.get("keys") or []
                if payload.get("vx") is not None:
                    result = self.session.drive(
                        float(payload.get("vx") or 0),
                        float(payload.get("vy") or 0),
                        float(payload.get("omega") or 0),
                    )
                else:
                    result = self.session.teleop_keys([str(item) for item in keys], slow=bool(payload.get("slow")))
                return self._json(200, result)
            if path == "/api/camera":
                return self._json(
                    200,
                    self.session.switch_camera(
                        str(payload.get("source") or ""),
                        int(payload.get("camera") or 0),
                    ),
                )
            if path == "/api/estop":
                self.session.estop()
                return self._json(200, self.session.state())
            if path == "/api/estop/clear":
                self.session.clear_estop()
                return self._json(200, self.session.state())
            if path == "/api/run":
                if payload.get("preset"):
                    return self._json(200, self.session.run_preset(str(payload["preset"])))
                return self._json(200, self.session.run_names([str(item) for item in payload.get("steps") or []]))
            if path == "/api/text":
                return self._json(200, self.session.handle_text(str(payload.get("text") or "")))
            if path == "/api/listen":
                return self._json(200, self.session.listen_once())
            if path == "/api/vision":
                return self._json(
                    200,
                    self.session.capture_vision(
                        speak=bool(payload.get("speak", True)),
                        question=str(payload.get("question") or payload.get("text") or ""),
                    ),
                )
            if path == "/api/campus":
                return self._json(
                    200,
                    self.session.configure_campus(
                        api_key=payload.get("api_key"),
                        api_url=payload.get("api_url"),
                        model=payload.get("model"),
                        extra=payload.get("extra"),
                        library_on=payload.get("library_on"),
                    ),
                )
            if path == "/api/program/run":
                return self._json(200, self.session.run_program(payload))
            if path == "/api/program/validate":
                return self._json(200, self.session.validate_program(payload))
            if path == "/api/program/inspect":
                return self._json(200, self.session.inspect_program(payload))
            if path == "/api/groups":
                return self._json(
                    200,
                    self.session.save_group(str(payload.get("name") or ""), [str(item) for item in payload.get("steps") or []]),
                )
            if path == "/api/groups/delete":
                return self._json(200, self.session.delete_group(str(payload.get("name") or "")))
        except Exception as error:
            return self._json(400, {"ok": False, "error": str(error)})
        self.send_error(404)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > 1_000_000:
            return {}
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _file(self, path: Path, mime: str) -> None:
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _mjpeg(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while True:
                jpeg = self.session.camera.jpeg
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ")
                self.wfile.write(str(len(jpeg)).encode())
                self.wfile.write(b"\r\n\r\n")
                self.wfile.write(jpeg)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
                import time

                time.sleep(0.07)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return


def serve(session: StudioSession, host: str, port: int) -> None:
    StudioHandler.session = session
    httpd = ThreadingHTTPServer((host, port), StudioHandler)
    print(f"教师控制台 http://{host}:{port}  （仅教师电脑本地使用，不要接到教学平台）", flush=True)
    httpd.serve_forever()
