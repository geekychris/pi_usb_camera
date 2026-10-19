<p align="center">
  <img src="assets/logo.png" alt="Pi Usb Camera logo" width="180">
</p>

# pi_usb_camera

Snapshot, video record, and live-stream from a USB webcam plugged into a
Raspberry Pi — driven from any workstation on the same network.

The Pi runs three tiny scripts (`snapshot.sh`, `record.sh`, `server.py`); your
Mac/Linux box has matching wrappers (`bin/snap`, `bin/rec`, `bin/serve`) that
SSH in, run the right script, and copy the result back. `bin/find` discovers
Raspberry Pis on the LAN so you don't need to remember the hostname.

Nothing is hard-coded to a specific Pi. Set `PI_HOST=user@host.local` (or pass
`--host`) and the same tooling works against any number of Pis.

## What you get

| concern             | tool                                  | result                                            |
| ------------------- | ------------------------------------- | ------------------------------------------------- |
| install deps        | `deploy.sh user@host`                 | rsyncs source + apt-installs ffmpeg / v4l-utils / flask |
| find Pis            | `bin/find`                            | mDNS + ARP-by-Pi-MAC-OUI sweep                    |
| snapshot            | `bin/snap [--host …] [out.jpg] [WxH]` | one JPEG → local file (opens in Preview on macOS) |
| record video        | `bin/rec  [--host …] [secs]`          | H.264 MP4 → local file                            |
| live stream         | `bin/serve [--host …]`                | `http://host:8080/` MJPEG in your browser         |
| background service  | `pi-camera.service` (systemd)         | auto-starts the stream on boot                    |

Snapshots and recordings use the camera's hardware-compressed output streams
(MJPEG for stills, H.264 for video) — no CPU re-encoding, the Pi 5 stays cool
even at 1080p30.

## Quickstart

```bash
git clone git@github.com:geekychris/pi_usb_camera.git
cd pi_usb_camera

# 1. Find your Pi (or just type its hostname).
bin/find

# 2. One-shot deploy: copy source, apt-install dependencies.
./deploy.sh chris@pi5.local

# 3. Set a default host so you don't keep typing it.
export PI_HOST=chris@pi5.local

# 4. Use it.
bin/snap                    # snapshot → ./snap-<date>.jpg
bin/rec 20                  # 20-second 1080p MP4 → ./rec-<date>.mp4
bin/serve                   # opens http://pi5.local:8080/ in your browser
```

To target a different Pi, override per-call: `bin/snap --host pi@pi4.local`.

## How it works (TL;DR)

- **snapshot.sh** drives `ffmpeg -f v4l2 -input_format mjpeg`. Grabs five
  frames so auto-exposure/auto-white-balance settles, keeps the last as JPEG.
- **record.sh** drives `ffmpeg -f v4l2 -input_format h264 -c:v copy`. The
  webcam encodes H.264 in hardware; we just remux into MP4.
- **server.py** runs one ffmpeg subprocess that streams native MJPEG from
  the camera. A reader thread splits the byte stream at JPEG SOI/EOI markers
  (`FFD8`/`FFD9`) and fans out the latest frame to every connected viewer via
  a `threading.Condition`. N viewers cost the same as one — the camera is
  only opened once. See [docs/architecture.md](docs/architecture.md).

## Layout

```
install.sh                  # runs on Pi: apt install + render systemd unit
snapshot.sh                 # runs on Pi: one JPEG
record.sh                   # runs on Pi: H.264 → MP4
server.py                   # runs on Pi: Flask MJPEG stream + index page
pi-camera.service.template  # rendered by install.sh into pi-camera.service
deploy.sh                   # local: rsync + install on chosen Pi

bin/find                    # local: discover Pis on the LAN
bin/snap                    # local: ssh + snapshot.sh + scp back + open
bin/rec                     # local: ssh + record.sh + scp back + open
bin/serve                   # local: ssh + server.py + open browser

docs/architecture.md        # design notes
docs/troubleshooting.md     # camera busy, port conflicts, low FPS, …
```

## Endpoints (web server)

| URL              | what it returns                                   |
| ---------------- | ------------------------------------------------- |
| `/`              | HTML page with the live image embedded            |
| `/stream.mjpg`   | raw `multipart/x-mixed-replace` MJPEG stream      |
| `/snapshot.jpg`  | single latest JPEG frame                          |

Stream endpoint is plain MJPEG over HTTP — any browser, VLC
(`Open Network Stream → http://host:8080/stream.mjpg`), or
`curl http://host:8080/snapshot.jpg -o still.jpg` works.

## Configuration

Environment variables, read by the local wrappers:

| var       | default          | meaning                                    |
| --------- | ---------------- | ------------------------------------------ |
| `PI_HOST` | *(none — error)* | default SSH target, e.g. `chris@pi5.local` |
| `PI_DEST` | `pi_usb_camera`  | install directory on the Pi (relative → user's `$HOME`) |

Environment variables, read by the Pi scripts (`snapshot.sh`, `record.sh`,
`server.py`):

| var             | default        | meaning                       |
| --------------- | -------------- | ----------------------------- |
| `CAMERA_DEVICE` | `/dev/video0`  | V4L2 device path              |
| `CAMERA_RES`    | `1280x720` (stream) / `1920x1080` (still/record) | resolution |
| `CAMERA_FPS`    | `30`           | server stream framerate       |

The server also accepts CLI args that override env vars:

```bash
~/pi_usb_camera/server.py --resolution 1920x1080 --framerate 25 --port 9000
```

## Run the server as a background service

`install.sh` renders `pi-camera.service` for the user/path of that install:

```bash
ssh chris@pi5.local
sudo cp ~/pi_usb_camera/pi-camera.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pi-camera
journalctl -u pi-camera -f      # follow logs
```

## Requirements

- A Raspberry Pi (any model with a USB port) running a Debian-based OS.
  Tested on a Pi 5 running Debian 13 (trixie).
- A UVC-class USB webcam — almost every USB webcam made in the last decade.
  `v4l2-ctl --list-devices` from the Pi confirms it's recognised.
- SSH access to the Pi from your workstation (key-based recommended).
- `rsync`, `ssh`, `scp` locally; `ffmpeg`, `v4l-utils`, `python3-flask` on
  the Pi — `deploy.sh` installs the Pi-side packages.

## Troubleshooting

See [docs/troubleshooting.md](docs/troubleshooting.md). Most common: another
service (`motion`, `raspi-cam-srv`, etc.) is already holding `/dev/video0` and
you get `Device or resource busy`. The fix is `sudo systemctl disable --now
<offender>`.

## License

MIT.
