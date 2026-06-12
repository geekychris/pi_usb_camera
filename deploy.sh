#!/bin/bash
# Sync the project to a Pi and run install.sh there.
# Run from your Mac. Host can be given as $1 or via PI_HOST env var.
# Usage: deploy.sh [user@host]
set -euo pipefail

HOST="${1:-${PI_HOST:-}}"
DEST="${PI_DEST:-pi_usb_camera}"
HERE="$(cd "$(dirname "$0")" && pwd)"

if [[ -z "$HOST" ]]; then
  cat >&2 <<EOF
error: no host. Provide one of:
  $0 user@host.local
  PI_HOST=user@host.local $0

Try \`bin/find\` to list Raspberry Pis on your network.
EOF
  exit 2
fi

echo "→ rsync $HERE/  →  $HOST:$DEST/"
rsync -avh --delete \
  --exclude '.git' \
  --exclude '.DS_Store' \
  --exclude 'captures/' \
  --exclude 'bin/' \
  --exclude 'docs/' \
  "$HERE/" "$HOST:$DEST/"

echo "→ install on $HOST"
ssh "$HOST" "bash $DEST/install.sh"
