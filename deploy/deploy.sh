#!/usr/bin/env bash
# Pull the latest code and restart the bot. Run on the VPS after pushing changes.
#
#   sudo ./deploy/deploy.sh
#
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/apocalyptbot}"
cd "$APP_DIR"

echo "==> Pulling latest code"
git pull --ff-only

if command -v docker >/dev/null 2>&1 && [ -f docker-compose.yml ] && docker compose ps >/dev/null 2>&1; then
    echo "==> Rebuilding and restarting Docker service"
    docker compose up -d --build
    docker compose ps
else
    echo "==> Updating virtualenv"
    ./.venv/bin/pip install --upgrade . >/dev/null
    echo "==> Restarting systemd service"
    systemctl restart apocalyptbot
    systemctl --no-pager status apocalyptbot | head -n 12
fi

echo "==> Done."
