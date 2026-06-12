# Architecture

This is a small project — three Pi scripts, three local wrappers, one Flask
app. This document explains *why* it's shaped the way it is and what
trade-offs were taken.

## The capture pipeline

A UVC webcam exposes one or more compressed pixel formats over USB. The
Creality 4MP cam this was built against supports four: MJPEG, H.264, HEVC,
and uncompressed YUYV. The Pi 5 has no hardware H.264 *encoder* (that was
dropped from VideoCore for the Pi 5), so the cheap path is:

- For **stills**, ask the camera for MJPEG, accept the first stable frame.
- For **video**, ask the camera for H.264, remux it into MP4. Zero CPU
  cost — ffmpeg just copies the bitstream.
- For **streaming**, ask the camera for MJPEG, fan the JPEG frames out to
  HTTP clients verbatim.

In each case the Pi never re-encodes pixels. That's why a 1080p30 stream
sits comfortably under 5% CPU on a Pi 5.

```
USB camera ─[USB UVC]─► /dev/video0 ─[V4L2]─► ffmpeg ─► snapshot.jpg / record.mp4 / MJPEG over HTTP
```

## Why ffmpeg, not OpenCV / picamera2 / mjpg-streamer

| tool                    | why we didn't                                                        |
| ----------------------- | -------------------------------------------------------------------- |
| OpenCV (`cv2`)          | heavy install, would JPEG-decode then re-encode each frame           |
| `picamera2`             | CSI-camera library; doesn't help with a USB UVC cam                  |
| `mjpg-streamer`         | works fine but is unmaintained and not in Debian trixie's main repo  |
| ffmpeg                  | in apt, fast, and supports `-input_format mjpeg / h264` over V4L2    |

## The MJPEG broker (server.py)

UVC cameras can only be opened by one process at a time. If `server.py`
spawned a new ffmpeg per HTTP request, the second viewer would get
`Device or resource busy`. The server therefore uses a **single ffmpeg
producer + broker fan-out** design:

```
                                       ┌── /stream.mjpg ── client A
ffmpeg (mjpeg → stdout) ──► reader ──► broker (Condition) ──► /stream.mjpg ── client B
                              │                              │
                              └── parses SOI/EOI markers     └── /snapshot.jpg (one frame)
```

- One `ffmpeg` subprocess: opened in `CameraBroker.start()`.
- A daemon thread reads from ffmpeg's stdout, scans for JPEG markers
  `\xFF\xD8` (SOI, start of image) and `\xFF\xD9` (EOI, end of image), and
  publishes each complete frame to `broker.frame` + bumps `broker.seq`.
- HTTP handlers call `broker.next_frame(last_seq)`, which blocks on a
  `Condition` until `seq` changes. Each handler tracks its own
  `last_seq`, so slow clients drop frames rather than blocking fast ones.
- `/snapshot.jpg` calls `broker.latest()`, which waits for the next fresh
  frame and returns it as a single JPEG response.

Net effect: N viewers cost almost exactly the same as one (just N goroutines
worth of memcpys). The camera is opened exactly once for the lifetime of
the server.

## Why no transcoding to WebRTC / HLS / WebM

MJPEG over `multipart/x-mixed-replace` is the dumbest possible streaming
protocol. It has three advantages:

- **Zero latency.** No GOPs, no segmenter, no buffer-ahead — the next
  JPEG hits the browser ~one frame after it leaves the camera.
- **Works everywhere.** Every browser since 2003, every IP-camera client,
  VLC, `ffplay`, even `curl`.
- **No CPU cost.** We literally pipe bytes — no encoding step on the Pi.

The cost is bandwidth: 720p30 MJPEG is ~3 MB/s, ~24 Mbit/s. For a LAN that's
trivial; for the public internet you'd want H.264 + HLS or WebRTC instead.
If you need that, see "Where to extend" below.

## SSH as control plane

Everything Mac-side is `ssh user@host '…'` followed by `scp`. There is no
custom daemon, no agent, no message bus. That's deliberate:

- The Pi can be vanilla Debian. No special config beyond `apt install`.
- Authentication is whatever your SSH config already provides (keys + agent
  forwarding usually).
- Debugging is `ssh chris@pi5.local` followed by running the same script
  yourself. There's no "control plane" layer to introspect.

Trade-off: each invocation pays one TCP handshake + SSH key exchange of
overhead. For one-shot snapshots / recordings that's fine (~250 ms). For
truly latency-critical use you'd run `server.py` permanently as a systemd
service and hit it over HTTP.

## Where to extend

- **Multiple cameras on one Pi.** Override `CAMERA_DEVICE=/dev/video2` per
  invocation, or run multiple `server.py` instances on different ports.
- **WebRTC / HLS.** Drop a `gst-launch-1.0` pipeline next to `server.py`,
  feed the camera's H.264 stream into it, expose RTC peer or HLS playlist.
- **Motion-triggered recording.** ffmpeg's `-vf select='gt(scene,0.05)'`
  works, but `motion` (apt package) is the standard tool for this.
- **Recording in parallel with streaming.** Two processes can't share
  `/dev/video0`. Either:
  - Run a single `ffmpeg` that tees the bitstream to two outputs (stream
    + file).
  - Or, structurally: have `server.py` own the camera and add a `/record`
    endpoint that writes its current frame queue to disk.
