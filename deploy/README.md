# Deploying Apocalyptbot

Unattended runs are **hunt** (watch books, place nothing) or **paper**
(simulated fills on live books). Live CLOB orders are attended-only:
`deploy/run.sh` exits if `MODE=live`, and the systemd unit must stay pointed
at that script.

Paper is only informative if it stays up through restarts and a working
heartbeat. Most people should never run `live`.

Two ways to run it. Pick one.

## Option A — systemd (no Docker)

Lightest footprint. Logs go to journald.

**1. As root, on a fresh Ubuntu/Debian VPS:**

```bash
git clone <your-repo-url> /opt/apocalyptbot
cd /opt/apocalyptbot
./deploy/bootstrap.sh
```

`bootstrap.sh` is idempotent. It does a small, boring set of things:

| Step | Why |
|------|-----|
| `apt` packages + `unattended-upgrades` | Security patches without a weekly SSH session |
| User `apocalypt` | The bot does not run as root |
| UFW | Default-deny inbound, SSH allowed. Does **not** `ufw reset` |
| fail2ban | Slows SSH password guessing |
| chrony | Resolution times and heartbeats need a sane clock |
| 2 GB swap, only if none exists | A memory spike should not OOM the box |
| venv + `pip install` | `/opt/apocalyptbot/.venv` |
| systemd unit | Enabled, **not** started |

It will not disable SSH passwords unless you re-run with `HARDEN_SSH=1`
**and** an `authorized_keys` file is already present.

If you already cloned the repo somewhere else, you can run
`sudo ./deploy/bootstrap.sh` from that tree; it copies into
`APP_DIR` (default `/opt/apocalyptbot`).

**2. Configure and start:**

```bash
nano /opt/apocalyptbot/.env     # MODE=hunt or MODE=paper
systemctl start apocalyptbot
journalctl -u apocalyptbot -f
```

**3. Later updates:**

```bash
sudo ./deploy/deploy.sh         # git pull, pip install, restart
```

`deploy.sh` refuses to continue if `.env` contains `MODE=live`.

## Option B — Docker

```bash
cp .env.example .env && ${EDITOR:-nano} .env
docker compose up -d --build
docker compose logs -f
```

`docker-compose.yml` sets `restart: unless-stopped`, caps memory at 1 GB,
rotates JSON logs, and bind-mounts `state/`, `logs/`, and `data/` so a
recreate does not wipe the paper book. The image runs as `apocalypt` and
probes `python3 -m apocalyptbot health`.

Still run the host-level parts of `bootstrap.sh` (firewall, fail2ban,
unattended-upgrades) if this VPS is on the public internet. A container
does not harden the box it sits on.

## What `deploy/run.sh` actually starts

| `MODE` | Command |
|--------|---------|
| `hunt` | `hunt --watch --poll $POLL_SECONDS --limit $HUNT_LIMIT` |
| `paper` | `paper --strategy $STRATEGY --cash $CASH --poll … --state --heartbeat` plus risk caps |
| `live` | refused (exit 2) |

`STRATEGY_PARAMS` (space-separated `key=value`) becomes repeated `--param`
flags on paper.

Hunt `--watch` does not go through the engine, so it does not write
`state/heartbeat`. `run.sh` keeps a small sidecar timestamp so Docker's
`HEALTHCHECK` and `apocalyptbot health` stay meaningful. Paper writes the
file itself each cycle.

## Monitoring

```bash
# systemd
journalctl -u apocalyptbot -f
/opt/apocalyptbot/.venv/bin/python -m apocalyptbot health

# Docker
docker compose logs -f
docker compose exec apocalyptbot python3 -m apocalyptbot health
```

Optional Telegram (`APOCALYPTBOT_TELEGRAM_TOKEN` + `_CHAT_ID`) or a
Discord/Slack webhook (`APOCALYPTBOT_WEBHOOK_URL`) notify on paper fills
and engine errors. Empty means silent.

## Checklist (do these; skip the rest of the internet's "hardening" theatre)

- [ ] `MODE=hunt` or `MODE=paper` in `.env`. Not live.
- [ ] `.env` is `chmod 600` and not in git (it is gitignored).
- [ ] SSH key works before you consider `HARDEN_SSH=1`.
- [ ] UFW is active and still lets you in.
- [ ] Heartbeat is fresh after a reboot (`systemctl` enable is already on).
- [ ] If you ever run `live` by hand: trade-only key, no withdrawal, IP pin
      if the wallet/proxy supports it, amount you can lose.

## Live trading is not a deploy target

CLOB V2 is live (2026). Live orders spend **pUSD** on Polygon 137 via
`py-clob-client-v2`. The systemd unit and this directory will not start
that loop. Sit at a terminal, set `POLYMARKET_PRIVATE_KEY`, and pass
`--i-understand-this-risks-real-money` if you truly mean it. Completeness
still dies to fees, latency, and size that vanished. Endgame and whale-copy
can zero the account.

This is not financial advice.
