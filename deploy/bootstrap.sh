#!/usr/bin/env bash
#
# One-shot provisioning + hardening for a fresh Ubuntu/Debian VPS, following
# the standard trading-bot-on-a-VPS checklist:
#   - system updates + automatic security patches (unattended-upgrades)
#   - non-root service user
#   - UFW firewall, default-deny inbound, SSH allowed
#   - fail2ban to throttle SSH brute-force
#   - time sync via chrony (mistimed candles = bad trades)
#   - swap file (so a memory spike doesn't OOM-kill the bot)
#   - the app itself: cloned, venv built, systemd service installed
#   - OPTIONAL, gated: SSH key-only login (never locks you out blindly)
#
# Run as root on the VPS:
#   ./deploy/bootstrap.sh [git_repo_url]
#
# Idempotent: safe to re-run. Review before running on a box you care about.
set -euo pipefail

APP_USER="${APP_USER:-apocalypt}"
APP_DIR="${APP_DIR:-/opt/apocalyptbot}"
REPO_URL="${1:-}"

log()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }

if [ "$(id -u)" -ne 0 ]; then
    echo "This script must run as root (try: sudo $0)" >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive

log "Updating system packages"
apt-get update -y
apt-get upgrade -y

log "Installing base packages"
apt-get install -y --no-install-recommends \
    git curl ca-certificates \
    python3 python3-venv python3-pip \
    ufw fail2ban unattended-upgrades chrony

log "Enabling automatic security updates"
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
systemctl enable --now unattended-upgrades || warn "unattended-upgrades not started"

log "Enabling time synchronization (chrony)"
systemctl enable --now chrony || systemctl enable --now chronyd || warn "chrony not started"

log "Configuring UFW firewall (default deny inbound, allow SSH)"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw --force enable
ufw status verbose || true

log "Enabling fail2ban (SSH brute-force protection)"
# A minimal, sensible sshd jail on top of the distro defaults.
cat >/etc/fail2ban/jail.d/apocalyptbot-sshd.local <<'EOF'
[sshd]
enabled  = true
maxretry = 5
findtime = 10m
bantime  = 1h
EOF
systemctl enable --now fail2ban
systemctl restart fail2ban || warn "fail2ban restart failed"

log "Ensuring a swap file exists"
if ! swapon --show | grep -q '/'; then
    fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >>/etc/fstab
    log "Created 2G swap file"
else
    log "Swap already present, skipping"
fi

log "Creating service user '$APP_USER'"
if ! id "$APP_USER" >/dev/null 2>&1; then
    useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
fi

log "Fetching the application into $APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
    git -C "$APP_DIR" pull --ff-only || warn "git pull failed; leaving existing checkout"
elif [ -n "$REPO_URL" ]; then
    git clone "$REPO_URL" "$APP_DIR"
else
    warn "No repo URL given and $APP_DIR has no checkout."
    warn "Copy the project to $APP_DIR manually, then re-run, or pass the git URL:"
    warn "    ./deploy/bootstrap.sh https://github.com/you/apocalyptbot.git"
fi

if [ -d "$APP_DIR" ]; then
    log "Building Python virtualenv and installing the bot"
    python3 -m venv "$APP_DIR/.venv"
    "$APP_DIR/.venv/bin/pip" install --upgrade pip >/dev/null
    "$APP_DIR/.venv/bin/pip" install "$APP_DIR"
    mkdir -p "$APP_DIR/state" "$APP_DIR/logs" "$APP_DIR/data"

    if [ ! -f "$APP_DIR/.env" ] && [ -f "$APP_DIR/.env.example" ]; then
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
        chmod 600 "$APP_DIR/.env"
        warn "Created $APP_DIR/.env from the example — EDIT IT before starting."
    fi
    chown -R "$APP_USER:$APP_USER" "$APP_DIR"
    chmod +x "$APP_DIR"/deploy/*.sh || true

    if [ -f "$APP_DIR/deploy/systemd/apocalyptbot.service" ]; then
        log "Installing systemd service"
        cp "$APP_DIR/deploy/systemd/apocalyptbot.service" /etc/systemd/system/
        systemctl daemon-reload
        systemctl enable apocalyptbot
        warn "Service installed & enabled but NOT started."
        warn "Edit $APP_DIR/.env, then: systemctl start apocalyptbot"
    fi
fi

# --- OPTIONAL: SSH key-only login (gated so you don't lock yourself out) -----
log "Checking SSH key setup before offering to disable password login"
KEYS_FOUND=0
for f in /root/.ssh/authorized_keys "/home/$SUDO_USER/.ssh/authorized_keys"; do
    [ -f "$f" ] && [ -s "$f" ] && KEYS_FOUND=1
done
if [ "${HARDEN_SSH:-0}" = "1" ] && [ "$KEYS_FOUND" = "1" ]; then
    log "Disabling SSH password authentication (HARDEN_SSH=1 and keys present)"
    sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
    sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
    systemctl reload ssh || systemctl reload sshd || warn "could not reload sshd"
else
    warn "SSH password login left ENABLED."
    warn "To harden: add your SSH public key to ~/.ssh/authorized_keys, then re-run with HARDEN_SSH=1."
fi

log "Done. Firewall, fail2ban, auto-updates, time sync and the service are set up."
echo
echo "Next steps:"
echo "  1. nano $APP_DIR/.env         # set strategy + (optional) Telegram alerts"
echo "  2. systemctl start apocalyptbot"
echo "  3. journalctl -u apocalyptbot -f"
