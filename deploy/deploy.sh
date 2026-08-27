#!/usr/bin/env bash
# Pull the latest code and restart hunt/paper. Run on the VPS after you push.
#
#   sudo ./deploy/deploy.sh
#
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/apocalyptbot}"
# If invoked from a checkout, prefer that tree.
if [ -f "$(cd "$(dirname "$0")/.." && pwd)/pyproject.toml" ]; then
    APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
fi
cd "$APP_DIR"

if [ -d .git ]; then
    echo "==> Pulling latest code"
    git pull --ff-only
fi

if [ -f .env ] && grep -qiE '^[[:space:]]*MODE=[[:space:]]*live' .env; then
    echo "refusing to deploy: .env has MODE=live" >&2
    echo "set MODE=hunt or MODE=paper. Live is attended-only." >&2
    exit 2
fi

if command -v docker >/dev/null 2>&1 && [ -f docker-compose.yml ] \
        && docker compose ps >/dev/null 2>&1; then
    echo "==> Rebuilding and restarting Docker service"
    docker compose up -d --build
    docker compose ps
else
    echo "==> Updating virtualenv"
    if [ ! -x .venv/bin/pip ]; then
        python3 -m venv .venv
    fi
    .venv/bin/pip install --upgrade . >/dev/null
    echo "==> Restarting systemd service"
    systemctl restart apocalyptbot
    systemctl --no-pager status apocalyptbot | head -n 12
fi

echo "==> Done."
