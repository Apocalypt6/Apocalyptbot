#!/usr/bin/env bash
#
# Light VPS bootstrap for Apocalyptbot (Ubuntu/Debian).
# Installs the package, a non-root service user, and a systemd unit that
# runs hunt or paper only — never live.
#
#   sudo ./deploy/bootstrap.sh [git_repo_url]
#
# Idempotent. Review before running on a box you already care about.
# This is not a full CIS guide: updates, a firewall that allows SSH,
# fail2ban, time sync, and a dedicated user. That is enough to start.
set -euo pipefail

APP_USER="${APP_USER:-apocalypt}"
APP_DIR="${APP_DIR:-/opt/apocalyptbot}"
REPO_URL="${1:-}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

log()  { printf '\n==> %s\n' "$*"; }
warn() { printf '[warn] %s\n' "$*"; }

if [ "$(id -u)" -ne 0 ]; then
    echo "This script must run as root (try: sudo $0)" >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive

log "Installing packages"
apt-get update -y
apt-get install -y --no-install-recommends \
    git curl ca-certificates rsync \
    python3 python3-venv python3-pip \
    ufw fail2ban unattended-upgrades chrony

log "Enabling automatic security updates"
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
systemctl enable --now unattended-upgrades 2>/dev/null || warn "unattended-upgrades not started"

log "Enabling time sync (chrony)"
systemctl enable --now chrony 2>/dev/null \
    || systemctl enable --now chronyd 2>/dev/null \
    || warn "chrony not started"

log "Firewall: allow SSH, deny other inbound (leaves existing extra rules alone)"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
if ! ufw status | grep -q "Status: active"; then
    ufw --force enable
fi
ufw status verbose || true

log "fail2ban: modest SSH jail"
mkdir -p /etc/fail2ban/jail.d
cat >/etc/fail2ban/jail.d/apocalyptbot-sshd.local <<'EOF'
[sshd]
enabled  = true
maxretry = 5
findtime = 10m
bantime  = 1h
EOF
systemctl enable --now fail2ban
systemctl restart fail2ban 2>/dev/null || warn "fail2ban restart failed"

if ! swapon --show | grep -q '/'; then
    log "Adding a 2G swap file (none present)"
    if fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none; then
        chmod 600 /swapfile
        mkswap /swapfile
        swapon /swapfile
        grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >>/etc/fstab
    else
        warn "could not create swap; continuing without it"
    fi
else
    log "Swap already present, leaving it"
fi

if ! id "$APP_USER" >/dev/null 2>&1; then
    log "Creating service user $APP_USER"
    useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
fi

log "Installing the application into $APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" pull --ff-only || warn "git pull failed; leaving existing checkout"
elif [ -n "$REPO_URL" ]; then
    git clone "$REPO_URL" "$APP_DIR"
elif [ -f "$REPO_ROOT/pyproject.toml" ] && [ "$REPO_ROOT" != "$APP_DIR" ]; then
    mkdir -p "$APP_DIR"
    rsync -a --exclude '.venv' --exclude 'state' --exclude 'logs' --exclude '.env' \
        "$REPO_ROOT"/ "$APP_DIR"/
    log "Copied local checkout $REPO_ROOT -> $APP_DIR"
elif [ -f "$REPO_ROOT/pyproject.toml" ]; then
    APP_DIR="$REPO_ROOT"
    log "Using existing checkout at $APP_DIR"
else
    warn "No repo URL given and $APP_DIR has no checkout."
    warn "Clone the project to $APP_DIR, or pass the git URL:"
    warn "    sudo ./deploy/bootstrap.sh https://github.com/you/apocalyptbot.git"
fi

if [ -d "$APP_DIR" ] && [ -f "$APP_DIR/pyproject.toml" ]; then
    log "Building venv and installing the package"
    python3 -m venv "$APP_DIR/.venv"
    "$APP_DIR/.venv/bin/pip" install --upgrade pip >/dev/null
    "$APP_DIR/.venv/bin/pip" install "$APP_DIR"
    mkdir -p "$APP_DIR/state" "$APP_DIR/logs" "$APP_DIR/data"
    chmod +x "$APP_DIR"/deploy/*.sh || true

    if [ ! -f "$APP_DIR/.env" ] && [ -f "$APP_DIR/.env.example" ]; then
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
        chmod 600 "$APP_DIR/.env"
        warn "Created $APP_DIR/.env from the example — edit MODE=hunt or paper before starting."
    elif [ -f "$APP_DIR/.env" ]; then
        chmod 600 "$APP_DIR/.env"
    fi

    chown -R "$APP_USER:$APP_USER" "$APP_DIR"

    if [ -f "$APP_DIR/deploy/systemd/apocalyptbot.service" ]; then
        log "Installing systemd unit (enabled, not started)"
        unit_src="$APP_DIR/deploy/systemd/apocalyptbot.service"
        unit_dst=/etc/systemd/system/apocalyptbot.service
        sed "s|/opt/apocalyptbot|$APP_DIR|g" "$unit_src" >"$unit_dst"
        systemctl daemon-reload
        systemctl enable apocalyptbot
        warn "Service installed and enabled, not started."
        warn "Edit $APP_DIR/.env (MODE=hunt or paper), then: systemctl start apocalyptbot"
    fi
fi

KEYS_FOUND=0
if [ -s /root/.ssh/authorized_keys ]; then
    KEYS_FOUND=1
fi
if [ -n "${SUDO_USER:-}" ] && [ -s "/home/$SUDO_USER/.ssh/authorized_keys" ]; then
    KEYS_FOUND=1
fi
if [ "${HARDEN_SSH:-0}" = "1" ] && [ "$KEYS_FOUND" = "1" ]; then
    log "Disabling SSH password login (HARDEN_SSH=1 and a key is present)"
    sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
    sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
    systemctl reload ssh 2>/dev/null || systemctl reload sshd 2>/dev/null \
        || warn "could not reload sshd"
else
    warn "SSH password login left enabled."
    warn "After your key is in ~/.ssh/authorized_keys, re-run with HARDEN_SSH=1 if you want key-only."
fi

log "Done."
echo
echo "Next steps:"
echo "  1. edit $APP_DIR/.env          # MODE=hunt or paper — never live"
echo "  2. systemctl start apocalyptbot"
echo "  3. journalctl -u apocalyptbot -f"
echo "  4. $APP_DIR/.venv/bin/python -m apocalyptbot health"
