#!/usr/bin/env bash
# Ubuntu 22.04 / 24.04 one-shot installer. Paper default. No keys required.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
DEST="${PULSE_DEST:-/opt/pulse5m}"
ENV_FILE="${PULSE_ENV:-/etc/pulse5m.env}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "re-run as root: sudo bash install.sh"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip chrony ca-certificates curl rsync git

id pulse5m >/dev/null 2>&1 || useradd --system --home "$DEST" --shell /usr/sbin/nologin pulse5m
mkdir -p "$DEST" /var/lib/pulse5m
rsync -a --exclude '.venv' --exclude 'data' --exclude '__pycache__' --exclude 'ROOT_README.md' --exclude 'ROOT_CURSOR.md' "$ROOT"/ "$DEST"/
python3 -m venv "$DEST/.venv"
"$DEST/.venv/bin/pip" install --upgrade pip
"$DEST/.venv/bin/pip" install -r "$DEST/requirements.txt"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$DEST/config.example.env" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi
if ! grep -q '^PULSE_DATA=' "$ENV_FILE"; then
  echo "PULSE_DATA=/var/lib/pulse5m" >> "$ENV_FILE"
fi

chown -R pulse5m:pulse5m "$DEST" /var/lib/pulse5m
chmod 750 "$DEST"

cp "$DEST/pulse5m.service" /etc/systemd/system/pulse5m.service
systemctl daemon-reload
systemctl enable --now chrony || true
systemctl enable pulse5m
systemctl restart pulse5m

echo
echo "installed."
echo "  health:  curl -s localhost:8080/health"
echo "  logs:    journalctl -u pulse5m -f"
echo "  probe:   sudo -u pulse5m $DEST/.venv/bin/python $DEST/bot.py --check"
echo "  live:    edit $ENV_FILE then systemctl edit pulse5m  (change --paper to --live)"
echo
echo "Paper is the default. There is no guaranteed edge."
