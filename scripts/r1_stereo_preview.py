"""电脑上单独看 R1 左右眼。不改教师控制台，也不走 video_hub。

画面在 Orin（默认 192.168.123.164）上收 stereo patch 的 H264，再转到本机网页。
官方 /dev/video-dep 没有时，深度用左右眼同一时刻做 SGBM，只供试看，不当安全距离。
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ORIN = os.environ.get("R1_ORIN", "unitree@192.168.123.164")
PASSWORD = os.environ.get("R1_ORIN_PASSWORD", "")
PORT = int(os.environ.get("R1_STEREO_PORT", "8766"))

PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<title>R1 左右眼试看</title>
<style>
body { font-family: sans-serif; background:#1b1033; color:#f4eefe; margin:0; }
header, .tools { padding:12px 16px; }
.row { display:flex; flex-wrap:nowrap; gap:8px; padding:0 12px 16px; align-items:flex-start; }
figure { margin:0; flex:1.21 1 0; min-width:0; background:#2c1658; border-radius:12px; padding:8px; }
figure.depth { flex:0.85 1 0; }
img, canvas { width:100%; height:auto; background:#000; border-radius:8px; display:block; touch-action:none; cursor:crosshair; }
figcaption { font-size:14px; margin-top:6px; }
small { color:#cbb7ef; }
button { background:#7c4dff; color:#fff; border:0; border-radius:8px; padding:8px 14px; margin-right:8px; font-size:15px; }
button:disabled { opacity:0.45; }
</style></head>
<body>
<header>
  <strong>左右眼试看</strong>
  <small id="status">连接中…</small>
  <p><small>深度图已裁掉左侧搜不到的边，只留能匹配的区域。机架仍只影响你涂过的四个角。</small></p>
</header>
<div class="row">
  <figure><img src="/left.mjpg" alt="左眼"/><figcaption>左眼 · UDP 5002</figcaption></figure>
  <figure><img src="/right.mjpg" alt="右眼"/><figcaption>右眼 · UDP 5003</figcaption></figure>
  <figure class="depth"><img src="/depth.mjpg" alt="深度"/><figcaption>深度 · 只保留有效区域</figcaption></figure>
</div>
<div class="tools">
  <button id="freeze" type="button">冻住当前左右眼</button>
  <button id="clear" type="button" disabled>清除涂抹</button>
  <button id="send" type="button" disabled>提交标记</button>
  <small id="markStatus">在冻住的画面上把机架涂红，再提交。</small>
</div>
<div class="row">
  <figure><canvas id="cLeft" width="544" height="448"></canvas><figcaption>左眼：涂右上角机架</figcaption></figure>
  <figure><canvas id="cRight" width="544" height="448"></canvas><figcaption>右眼：涂左上角机架</figcaption></figure>
</div>
<script>
const pads = {};
const shots = {};
function pad(id) {
  const canvas = document.getElementById(id);
  const mask = document.createElement("canvas");
  const image = new Image();
  let drawing = false;
  let last = null;
  function redraw() {
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (image.src) ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    ctx.drawImage(mask, 0, 0);
  }
  function pos(ev) {
    const r = canvas.getBoundingClientRect();
    return [
      (ev.clientX - r.left) * canvas.width / r.width,
      (ev.clientY - r.top) * canvas.height / r.height,
    ];
  }
  function stroke(ev) {
    if (!drawing) return;
    const [x, y] = pos(ev);
    const ctx = mask.getContext("2d");
    ctx.strokeStyle = "rgba(255,48,48,0.9)";
    ctx.lineWidth = 28;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(last[0], last[1]);
    ctx.lineTo(x, y);
    ctx.stroke();
    last = [x, y];
    redraw();
  }
  canvas.addEventListener("pointerdown", (ev) => {
    if (!image.src) return;
    drawing = true;
    last = pos(ev);
    stroke(ev);
    canvas.setPointerCapture(ev.pointerId);
  });
  canvas.addEventListener("pointermove", stroke);
  canvas.addEventListener("pointerup", () => { drawing = false; });
  canvas.addEventListener("pointercancel", () => { drawing = false; });
  return {
    mask, image, redraw,
    clear() {
      mask.getContext("2d").clearRect(0, 0, mask.width, mask.height);
      redraw();
    },
  };
}
pads.cLeft = pad("cLeft");
pads.cRight = pad("cRight");

async function still(url, slot) {
  const blob = await (await fetch(url, { cache: "no-store" })).blob();
  shots[slot] = blob;
  const img = pads[slot].image;
  img.onload = () => {
    const canvas = document.getElementById(slot);
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    pads[slot].mask.width = img.naturalWidth;
    pads[slot].mask.height = img.naturalHeight;
    pads[slot].clear();
  };
  img.src = URL.createObjectURL(blob);
  await img.decode();
}

document.getElementById("freeze").onclick = async () => {
  document.getElementById("markStatus").textContent = "正在冻住…";
  await Promise.all([still("/left.jpg", "cLeft"), still("/right.jpg", "cRight")]);
  document.getElementById("clear").disabled = false;
  document.getElementById("send").disabled = false;
  document.getElementById("markStatus").textContent = "已冻住。涂红机架后点提交。";
  document.getElementById("cLeft").scrollIntoView({ behavior: "smooth", block: "center" });
};
document.getElementById("clear").onclick = () => {
  pads.cLeft.clear();
  pads.cRight.clear();
};
function asData(blob) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.readAsDataURL(blob);
  });
}
document.getElementById("send").onclick = async () => {
  document.getElementById("markStatus").textContent = "提交中…";
  const res = await fetch("/api/mark", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      left_jpg: await asData(shots.cLeft),
      right_jpg: await asData(shots.cRight),
      left_mask: pads.cLeft.mask.toDataURL("image/png"),
      right_mask: pads.cRight.mask.toDataURL("image/png"),
    }),
  });
  const data = await res.json();
  document.getElementById("markStatus").textContent = data.note || "已提交";
};

async function tick() {
  try {
    const data = await (await fetch("/api/status")).json();
    document.getElementById("status").textContent =
      "左 " + data.left_age + "s · 右 " + data.right_age + "s · " + (data.note || "");
  } catch (err) {}
}
setInterval(tick, 1000); tick();
</script>
</body></html>
"""


def _wls_depth(left, right, previous):
    """左右眼视差：SGBM + 右视差一致性 + WLS，再中值和时间平滑。"""
    import cv2
    import numpy as np

    height, width = left.shape[:2]
    if width > 480:
        scale = 480 / width
        size = (480, max(1, int(height * scale)))
        left = cv2.resize(left, size)
        right = cv2.resize(right, size)
    gray_l = cv2.cvtColor(left, cv2.COLOR_BGR2GRAY)
    gray_r = cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)
    matcher = cv2.StereoSGBM_create(
        minDisparity=0,
        numDisparities=64,
        blockSize=7,
        P1=8 * 3 * 49,
        P2=32 * 3 * 49,
        uniquenessRatio=15,
        speckleWindowSize=100,
        speckleRange=1,
        disp12MaxDiff=1,
        mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY,
    )
    right_matcher = cv2.ximgproc.createRightMatcher(matcher)
    wls = cv2.ximgproc.createDisparityWLSFilter(matcher)
    wls.setLambda(8000)
    wls.setSigmaColor(1.5)
    disp_l = matcher.compute(gray_l, gray_r)
    disp_r = right_matcher.compute(gray_r, gray_l)
    filtered = wls.filter(disp_l, left, None, disp_r).astype(np.float32) / 16.0
    confidence = wls.getConfidenceMap()
    filtered[(filtered < 0.5) | (confidence < 20)] = 0
    filtered = cv2.medianBlur(filtered, 5)
    if previous is not None and previous.shape == filtered.shape:
        both = (filtered > 0.5) & (previous > 0.5)
        filtered = filtered.copy()
        filtered[both] = 0.65 * previous[both] + 0.35 * filtered[both]
    valid = filtered > 0.5
    vis = np.zeros(filtered.shape, np.uint8)
    vis[valid] = np.clip(filtered[valid] * (255.0 / 48.0), 0, 255).astype(np.uint8)
    color = cv2.applyColorMap(vis, cv2.COLORMAP_TURBO)
    color[~valid] = (48, 48, 48)
    return color, filtered


class Eyes:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.left = b""
        self.right = b""
        self.depth = b""
        self.left_t = 0.0
        self.right_t = 0.0
        self.note = "等待左右眼"
        self._ask = ""
        self._disp_prev = None

    def start(self) -> None:
        handle = tempfile.NamedTemporaryFile("w", delete=False, prefix="r1ask-")
        handle.write("#!/bin/sh\necho %s\n" % PASSWORD.replace("'", "'\\''"))
        handle.close()
        os.chmod(handle.name, 0o700)
        self._ask = handle.name
        threading.Thread(target=self._pull, args=(5002, "left"), daemon=True).start()
        threading.Thread(target=self._pull, args=(5003, "right"), daemon=True).start()
        threading.Thread(target=self._depth_loop, daemon=True).start()

    def _ssh(self, remote: str) -> subprocess.Popen:
        env = os.environ.copy()
        env["DISPLAY"] = "none"
        env["SSH_ASKPASS"] = self._ask
        env["SSH_ASKPASS_REQUIRE"] = "force"
        return subprocess.Popen(
            [
                "setsid",
                "-w",
                "ssh",
                "-o",
                "PreferredAuthentications=password",
                "-o",
                "PubkeyAuthentication=no",
                "-o",
                "StrictHostKeyChecking=accept-new",
                ORIN,
                remote,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )

    def _pull(self, port: int, which: str) -> None:
        remote = (
            "gst-launch-1.0 -q udpsrc port=%d "
            "caps=application/x-rtp,media=video,clock-rate=90000,encoding-name=H264,payload=96 "
            "! rtph264depay ! avdec_h264 ! videoconvert ! jpegenc quality=60 "
            "! fdsink fd=1 sync=false"
        ) % port
        while True:
            proc = self._ssh(remote)
            buf = b""
            assert proc.stdout is not None
            try:
                while True:
                    chunk = proc.stdout.read(8192)
                    if not chunk:
                        break
                    buf += chunk
                    while True:
                        start = buf.find(b"\xff\xd8")
                        if start < 0:
                            buf = buf[-1:]
                            break
                        end = buf.find(b"\xff\xd9", start + 2)
                        if end < 0:
                            buf = buf[start:]
                            break
                        frame = buf[start : end + 2]
                        buf = buf[end + 2 :]
                        with self.lock:
                            if which == "left":
                                self.left = frame
                                self.left_t = time.time()
                            else:
                                self.right = frame
                                self.right_t = time.time()
            finally:
                proc.kill()
            time.sleep(1.0)

    def _depth_loop(self) -> None:
        import cv2
        import numpy as np

        from r1_studio.depth import stereo_map

        while True:
            time.sleep(0.2)
            with self.lock:
                left_b, right_b = self.left, self.right
                ages = (time.time() - self.left_t, time.time() - self.right_t)
            if not left_b or not right_b or max(ages) > 1.5:
                continue
            left = cv2.imdecode(np.frombuffer(left_b, np.uint8), cv2.IMREAD_COLOR)
            right = cv2.imdecode(np.frombuffer(right_b, np.uint8), cv2.IMREAD_COLOR)
            if left is None or right is None:
                continue
            _disp, color, _small = stereo_map(left, right)
            if color is None:
                continue
            # SGBM 左缘 numDisparities 列没有搜索范围，预览里裁掉。
            color = color[:, 96:]
            if color.size == 0:
                continue
            ok, encoded = cv2.imencode(".jpg", color, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if not ok:
                continue
            with self.lock:
                self.depth = encoded.tobytes()
                self.note = "去噪已关，原始 SGBM"

    def status(self) -> dict:
        now = time.time()
        with self.lock:
            return {
                "left_age": round(now - self.left_t, 1) if self.left_t else None,
                "right_age": round(now - self.right_t, 1) if self.right_t else None,
                "note": self.note,
            }


EYES = Eyes()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        if args and "mjpg" in str(args[0]):
            return
        super().log_message(fmt, *args)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/status":
            import json

            body = json.dumps(EYES.status(), ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        still = {"/left.jpg": "left", "/right.jpg": "right"}.get(path)
        if still:
            with EYES.lock:
                jpeg = getattr(EYES, still)
            if not jpeg:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(jpeg)))
            self.end_headers()
            self.wfile.write(jpeg)
            return
        slot = {"/left.mjpg": "left", "/right.mjpg": "right", "/depth.mjpg": "depth"}.get(path)
        if slot:
            self._mjpeg(slot)
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        import base64
        import json

        path = self.path.split("?", 1)[0]
        if path != "/api/mark":
            self.send_error(404)
            return
        size = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(size) or b"{}")
        folder = "/tmp/r1_stereo_marks"
        os.makedirs(folder, exist_ok=True)

        def write_data(name: str, value: str) -> None:
            raw = value or ""
            if "," in raw:
                raw = raw.split(",", 1)[1]
            if raw:
                open(os.path.join(folder, name), "wb").write(base64.b64decode(raw))

        write_data("left.jpg", payload.get("left_jpg") or "")
        write_data("right.jpg", payload.get("right_jpg") or "")
        write_data("left_mask.png", payload.get("left_mask") or "")
        write_data("right_mask.png", payload.get("right_mask") or "")
        note = "标记已保存"
        body = json.dumps({"ok": True, "note": note}, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _mjpeg(self, slot: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        try:
            while True:
                with EYES.lock:
                    jpeg = getattr(EYES, slot)
                if jpeg:
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n")
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
                time.sleep(0.08)
        except (BrokenPipeError, ConnectionResetError):
            return


def main() -> None:
    if not PASSWORD:
        raise SystemExit("请设置 R1_ORIN_PASSWORD 后再看左右眼")
    EYES.start()
    print("左右眼试看 http://127.0.0.1:%d  （教师控制台仍是 8765，这页不改它）" % PORT, flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
