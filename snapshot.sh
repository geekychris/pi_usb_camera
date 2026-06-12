#!/bin/bash
# Take one JPEG from the USB camera.
# Usage: snapshot.sh [output.jpg] [WIDTHxHEIGHT]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$HERE/captures/snap-$(date +%Y%m%d-%H%M%S).jpg}"
RES="${2:-1920x1080}"
DEV="${CAMERA_DEVICE:-/dev/video0}"

mkdir -p "$(dirname "$OUT")"

# Capture a few native-MJPEG frames so AE/AWB settles; keep the last via -update 1.
ffmpeg -y -hide_banner -loglevel error \
  -f v4l2 -input_format mjpeg -video_size "$RES" -i "$DEV" \
  -frames:v 5 -update 1 -q:v 2 "$OUT"

echo "$OUT"
