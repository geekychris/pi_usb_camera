#!/usr/bin/env python3
"""USB-camera MJPEG streamer.

One ffmpeg subprocess reads native MJPEG from the camera. A reader thread
slices the byte stream at JPEG SOI/EOI markers and publishes the latest
frame to all connected viewers via a Condition — N viewers cost the same
as one, since the camera is only opened once.
"""
import argparse
import os
import signal
import subprocess
import sys
import threading
from flask import Flask, Response, abort

app = Flask(__name__)


class CameraBroker:
    SOI = b"\xff\xd8"
    EOI = b"\xff\xd9"

    def __init__(self, device, resolution, framerate):
        self.device = device
        self.resolution = resolution
        self.framerate = framerate
        self.cond = threading.Condition()
        self.frame = None
        self.seq = 0
        self.running = False
        self.proc = None
        self.thread = None

    def start(self):
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "v4l2",
            "-input_format", "mjpeg",
            "-video_size", self.resolution,
            "-framerate", str(self.framerate),
            "-i", self.device,
            "-c:v", "copy",
            "-f", "mjpeg", "-",
        ]
        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0
        )
        self.running = True
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def _reader(self):
        buf = b""
        try:
            while self.running:
                chunk = self.proc.stdout.read(65536)
                if not chunk:
                    break
                buf += chunk
                while True:
                    s = buf.find(self.SOI)
                    if s < 0:
                        buf = b""
                        break
                    e = buf.find(self.EOI, s + 2)
                    if e < 0:
                        if s > 0:
                            buf = buf[s:]
                        break
                    frame = buf[s:e + 2]
                    buf = buf[e + 2:]
                    with self.cond:
                        self.frame = frame
                        self.seq += 1
                        self.cond.notify_all()
        finally:
            with self.cond:
                self.running = False
                self.cond.notify_all()

    def next_frame(self, last_seq, timeout=10.0):
        with self.cond:
            while self.running and self.seq == last_seq:
                if not self.cond.wait(timeout=timeout):
                    return None, last_seq
            return self.frame, self.seq

    def latest(self, timeout=5.0):
        with self.cond:
            start = self.seq
            while self.running and (self.frame is None or self.seq == start):
                if not self.cond.wait(timeout=timeout):
                    return None
            return self.frame

    def stop(self):
        self.running = False
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()


broker: CameraBroker | None = None


@app.route("/")
def index():
    assert broker is not None
    return f"""<!doctype html>
<html><head>
<meta charset="utf-8"/>
<title>USB camera</title>
<style>
  html, body {{ margin:0; background:#111; color:#eee; font-family:system-ui,sans-serif; }}
  header {{ padding:.6rem 1rem; background:#222; display:flex; gap:1rem; align-items:center; }}
  header a {{ color:#9cf; text-decoration:none; }}
  header a:hover {{ text-decoration:underline; }}
  main {{ display:flex; justify-content:center; padding:1rem; }}
  img {{ max-width:100%; height:auto; box-shadow:0 0 24px #000a; }}
  code {{ background:#000; padding:.1em .4em; border-radius:3px; }}
</style>
</head><body>
<header>
  <strong>USB camera</strong>
  <span>{broker.resolution} @ {broker.framerate}fps</span>
  <a href="/snapshot.jpg" download>snapshot</a>
  <a href="/stream.mjpg" target="_blank">raw stream</a>
</header>
<main><img src="/stream.mjpg" alt="live"/></main>
</body></html>
"""


@app.route("/stream.mjpg")
def stream():
    assert broker is not None

    def gen():
        last_seq = 0
        while True:
            frame, last_seq = broker.next_frame(last_seq)
            if frame is None:
                break
            yield b"--frame\r\n"
            yield b"Content-Type: image/jpeg\r\nContent-Length: " + str(len(frame)).encode() + b"\r\n\r\n"
            yield frame
            yield b"\r\n"

    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/snapshot.jpg")
def snapshot():
    assert broker is not None
    frame = broker.latest()
    if frame is None:
        abort(503)
    return Response(frame, mimetype="image/jpeg")


def main():
    global broker
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--device", default=os.environ.get("CAMERA_DEVICE", "/dev/video0"))
    ap.add_argument("--resolution", default=os.environ.get("CAMERA_RES", "1280x720"))
    ap.add_argument("--framerate", type=int, default=int(os.environ.get("CAMERA_FPS", "30")))
    args = ap.parse_args()

    broker = CameraBroker(args.device, args.resolution, args.framerate)
    broker.start()

    def _stop(*_):
        broker.stop()
        sys.exit(0)
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    print(
        f"pi-camera: http://{args.host}:{args.port}/  "
        f"device={args.device}  {args.resolution}@{args.framerate}fps",
        flush=True,
    )
    app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
