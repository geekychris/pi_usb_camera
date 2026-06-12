#!/bin/bash
# Runs ON the Pi. Installs apt packages and renders a systemd unit
# parameterised for the current user and install path.
set -euo pipefail

PKGS=(v4l-utils ffmpeg python3-flask)

missing=()
for p in "${PKGS[@]}"; do
  dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p")
done

if (( ${#missing[@]} > 0 )); then
  echo "→ apt install: ${missing[*]}"
  sudo apt-get update
  sudo apt-get install -y "${missing[@]}"
else
  echo "→ all packages already installed"
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="$(id -un)"

mkdir -p "$HERE/captures"
chmod +x "$HERE/snapshot.sh" "$HERE/record.sh" "$HERE/server.py" "$HERE/install.sh"

# Render the systemd unit so paths and User= match this install.
if [[ -f "$HERE/pi-camera.service.template" ]]; then
  sed -e "s|__USER__|$USER_NAME|g" -e "s|__HERE__|$HERE|g" \
    "$HERE/pi-camera.service.template" > "$HERE/pi-camera.service"
fi

cat <<EOF

✓ install complete
  snapshot:  $HERE/snapshot.sh [out.jpg] [WxH]
  record:    $HERE/record.sh   [out.mp4] [seconds] [WxH]
  stream:    $HERE/server.py   (then open http://\$(hostname).local:8080)

To run the server as a background service:
  sudo cp $HERE/pi-camera.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now pi-camera
EOF
