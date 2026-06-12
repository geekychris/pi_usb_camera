# Troubleshooting

## `Device or resource busy` opening `/dev/video0`

Something else has the camera open. UVC devices allow exactly one consumer
of the video-capture node at a time. Common culprits on Raspberry Pi OS:

- `motion.service` — motion-detection daemon.
- `raspiCamSrv.service` — third-party camera web UI.
- `mjpg_streamer` running from a previous install.
- Your own `server.py` already running in the background.

Find the holder, stop it:

```bash
ssh user@host
ps -ef | grep -E "ffmpeg|motion|raspiCamSrv|server\.py" | grep -v grep
sudo systemctl disable --now motion.service      # adjust to the offender
```

Verify the device is now free:

```bash
ls -l /proc/*/fd/* 2>/dev/null | grep -E "video0|media" || echo "free"
```

(A `wireplumber` handle on `/dev/mediaN` is normal — that's PipeWire's
device-enumeration probe, it doesn't block capture.)

## `apt install` fails with "Could not get lock"

Something else (unattended-upgrades, hpijs plugin installer, etc.) is
running `apt`. Wait a couple minutes and retry. If stuck:

```bash
sudo lsof /var/lib/dpkg/lock-frontend
sudo systemctl stop unattended-upgrades   # if that's the holder
```

## Stream works on the Pi but my browser shows a broken image

- **Wrong port.** Server defaults to `:8080`. `bin/serve --port 9000` works,
  but make sure the browser URL matches.
- **mDNS not resolving.** `pi5.local` only works if your OS supports mDNS
  (macOS does natively; on Linux make sure `avahi-daemon` runs). Fallback:
  use the Pi's LAN IP — `bin/find` will print it.
- **Server crashed.** SSH to the Pi and run `python3 ~/pi_usb_camera/server.py`
  in the foreground; you'll see ffmpeg's error in stderr.

## Stream is laggy or low FPS

- The camera might be in YUYV/uncompressed mode. Check
  `v4l2-ctl -d /dev/video0 --list-formats-ext` — `MJPG` should be listed.
  If it's not, the camera isn't UVC-MJPEG-capable and the Pi has to
  re-encode (expensive).
- Wi-Fi can be the bottleneck. 720p30 MJPEG is ~25 Mbit/s. On a flaky 2.4
  GHz connection, drop the resolution:
  `bin/serve --resolution 640x480 --framerate 15`.
- Many ARP/route-flapping problems show up as "stream pauses every few
  seconds." `ping -i 0.2 pi5.local` from your Mac will show the gaps.

## `bin/snap` returns a 12 KB JPEG

That's a valid JPEG of a flat scene (lens cap on, dark room, plain wall).
The capture is fine; the encoder just produced a small file because there
was nothing to encode. Point the camera at something detailed to confirm.

## Recording errors out: "h264 not supported"

Your camera may not expose H.264 over UVC. Check:

```bash
v4l2-ctl -d /dev/video0 --list-formats-ext | grep -i h264
```

If empty, edit `record.sh`: change `-input_format h264 ... -c:v copy` to
`-input_format mjpeg ... -c:v libx264 -preset veryfast -crf 23`. That
encodes on the CPU instead — slower (~30-50% CPU at 1080p30 on a Pi 5)
but works with any UVC camera.

## `bin/find` shows nothing

- **macOS:** `dns-sd` is built in; the mDNS section should always work if
  any Pi is on your network. ARP cache may be empty if you've never
  contacted the Pi — `ping pi5.local` once and rerun.
- **Linux:** install `avahi-utils` (`sudo apt install avahi-utils`).
- Some routers (especially corporate / mesh setups) block multicast across
  subnets. `bin/find` only sees Pis on the same broadcast domain.

## systemd service won't start

`journalctl -u pi-camera -n 50` will show why. Most common:

- Wrong user / path because `install.sh` wasn't re-run after moving the
  install directory. Re-run it, re-copy the unit:
  ```bash
  bash ~/pi_usb_camera/install.sh
  sudo cp ~/pi_usb_camera/pi-camera.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl restart pi-camera
  ```
- Port already bound (e.g. you're already running `server.py` interactively).
  `ss -tlnp | grep 8080` finds the holder.

## SSH asks for a password every time

You haven't added your public key to the Pi yet. From your Mac:

```bash
ssh-copy-id chris@pi5.local
```

The wrappers run multiple ssh/scp commands per invocation; without key
auth you'll get prompted three times for one snapshot.
