#!/usr/bin/env bash
# Thin wrapper so the README can say: bash deploy.sh
set -euo pipefail
cd "$(dirname "$0")"
chmod +x install.sh
if [[ "$(id -u)" -eq 0 ]]; then
  exec bash install.sh
fi
if command -v sudo >/dev/null; then
  exec sudo bash install.sh
fi
echo "need root (or sudo) to install systemd + chrony"
exit 1
