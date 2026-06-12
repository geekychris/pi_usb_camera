#!/bin/bash
# Record video from the USB camera using its native H.264 bitstream (no CPU encode).
# Usage: record.sh [output.mp4] [seconds] [WIDTHxHEIGHT]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$HERE/captures/rec-$(date +%Y%m%d-%H%M%S).mp4}"
SECS="${2:-10}"
RES="${3:-1920x1080}"
DEV="${CAMERA_DEVICE:-/dev/video0}"

mkdir -p "$(dirname "$OUT")"

ffmpeg -y -hide_banner -loglevel error \
  -f v4l2 -input_format h264 -video_size "$RES" -framerate 30 -i "$DEV" \
  -t "$SECS" -c:v copy -movflags +faststart "$OUT"

echo "$OUT"
