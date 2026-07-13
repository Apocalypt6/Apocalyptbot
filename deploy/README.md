# Running Apocalyptbot 24/7 on a VPS

This guide takes you from a fresh Linux VPS to a hardened box running the bot
around the clock, following the widely-recommended trading-bot deployment
checklist (auto-restart, firewall, fail2ban, auto-updates, time sync,
monitoring). It reflects current best practice — see [Sources](#sources).

> **Golden rule:** run in **paper mode for at least ~2 weeks** and confirm the
> logs, restarts, and alerts all behave before you even think about real money.
> Going live also requires a live broker adapter, which isn't built yet.

There are two supported ways to run it. Pick one.

---

## Option A — systemd (no Docker)

Best if you want the lightest footprint and native journald logs.

**1. Provision + harden the box (as root):**

```bash
git clone <your-repo-url> /opt/apocalyptbot
cd /opt/apocalyptbot
./deploy/bootstrap.sh
```

`bootstrap.sh` is idempotent and does all of this for you:

| Step | What & why |
|------|------------|
| System update + `unattended-upgrades` | Auto-installs security patches — highest-impact, lowest-effort protection |
| Non-root `apocalypt` user | The bot never runs as root |
| UFW firewall | Default-deny inbound, only SSH allowed |
| fail2ban | Bans IPs after repeated failed SSH logins |
| chrony | Keeps the clock accurate so candle timestamps are correct |
| 2 GB swap | A memory spike can't OOM-kill the bot |
| venv + install | Builds `/opt/apocalyptbot/.venv` and installs the package |
| systemd service | Installs, enables (start-on-boot), but doesn't start yet |

**2. Configure and start:**

```bash
nano /opt/apocalyptbot/.env        # strategy, symbol, optional Telegram alerts
systemctl start apocalyptbot
journalctl -u apocalyptbot -f      # watch it work
```

**3. Lock down SSH (recommended).** Make sure your public key is in
`~/.ssh/authorized_keys`, confirm you can log in with it, then:

```bash
HARDEN_SSH=1 ./deploy/bootstrap.sh   # disables SSH password login
```

The script refuses to disable passwords unless a key is present — so it won't
lock you out.

**Update later:** `sudo ./deploy/deploy.sh` (pulls, reinstalls, restarts).

---

## Option B — Docker

Best if you like container isolation and easy rollbacks.

```bash
# after installing Docker + the compose plugin, and cloning the repo:
cp .env.example .env && nano .env
docker compose up -d --build
docker compose logs -f
```

`docker-compose.yml` sets `restart: unless-stopped` (survives crashes and
reboots), caps memory at 1 GB, rotates logs, and persists `state/` so the
portfolio and heartbeat survive restarts. The image ships a `HEALTHCHECK` that
marks the container unhealthy if the heartbeat goes stale.

Still run the firewall/fail2ban/auto-update parts of `bootstrap.sh` on the host
even when using Docker — containers don't harden the box they run on.

---

## Configuration

All behaviour is driven by `.env` (see [`.env.example`](../.env.example)).
The key knobs:

```ini
STRATEGY=sma_crossover
SYMBOL=BTC-USD
INTERVAL=1h
STRATEGY_PARAMS=fast=10 slow=30
POLL_SECONDS=3600
```

`deploy/run.sh` turns these into the right `python -m apocalyptbot paper ...`
command, so both systemd and Docker read the same single source of truth.

## Monitoring & alerts

- **Heartbeat:** every cycle writes a unix timestamp to `state/heartbeat`.
  Check freshness anytime:
  ```bash
  python -m apocalyptbot health --heartbeat state/heartbeat --max-age 900
  ```
  This is also the Docker `HEALTHCHECK` and a good target for an external
  uptime monitor or a cron alert.
- **Push alerts:** set `APOCALYPTBOT_TELEGRAM_TOKEN` + `..._CHAT_ID`, or
  `APOCALYPTBOT_WEBHOOK_URL` (Discord/Slack). You'll get a message on startup,
  on every fill, and on any error in the loop. If nothing is configured, alerts
  are silently skipped.
- **Logs:** `journalctl -u apocalyptbot -f` (systemd) or
  `docker compose logs -f` (Docker).

## Security checklist (do all of these)

- [ ] SSH key-only login, root password login disabled (`HARDEN_SSH=1`)
- [ ] UFW enabled, default-deny inbound (bootstrap does this)
- [ ] fail2ban running (bootstrap does this)
- [ ] Automatic security updates on (bootstrap does this)
- [ ] Bot runs as the non-root `apocalypt` user (service/container default)
- [ ] `.env` is `chmod 600` and **never committed** (it's gitignored)
- [ ] When you go live: exchange keys are **trade-only, withdrawals disabled**,
      and **IP-whitelisted** to this VPS

## Before going live (later)

1. Paper-trade the exact strategy + params on the VPS for ~2 weeks.
2. Verify restart-on-reboot, alerting, and heartbeat all fire.
3. Add a live broker adapter (roadmap) behind the same `buy`/`sell` interface.
4. Start with an amount you are 100% willing to lose, with hard risk limits.

## Sources

- [How to Run a Trading Bot 24/7: VPS Setup Guide (2026) — SmartMoneyPath](https://smartmoneypath.io/how-to-run-a-trading-bot-24-7-vps-setup-guide-2026/)
- [Crypto Trading Bot Docker 2026 Containerization Guide — XCryptoBot](https://xcryptobot.com/blog/crypto-bot-docker-2026-containerization-guide)
- [VPS Hosting for Trading Bots: Server Setup & Infrastructure Guide — DEV](https://dev.to/vathsaman/vps-hosting-for-trading-botsserver-setup-infrastructure-guide-4n26)
- [Ubuntu 24.04 VPS Security Hardening Guide — MassiveGRID](https://massivegrid.com/blog/ubuntu-vps-security-hardening-guide/)
- [VPS Security Hardening Checklist (2026) — USAVPS](https://usavps.com/blog/post/vps-security-audit-checklist-hardening-2026/)
