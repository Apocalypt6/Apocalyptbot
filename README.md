# Apocalyptbot

Two bots live in this repo.

1. **Pulse 5M** (`pulse5m/`) — Polymarket 5-minute crypto Up/Down worker (BTC, ETH, SOL, XRP). This is the one you deploy on the new VPS.
2. **Coinbase paper bot** (`apocalyptbot/`) — older SMA / RSI / DCA simulator. Leave it alone unless you want that.

Paper is the default. No private keys belong in this repository.

---

## Pulse 5M — deploy on the VPS

```bash
git clone https://github.com/Apocalypt6/Apocalyptbot.git
cd Apocalyptbot/pulse5m
sudo bash deploy.sh
curl -s localhost:8080/health
journalctl -u pulse5m -f
```

That installs chrony, a venv, user `pulse5m`, and a systemd unit in **paper**.

Prove the feeds:

```bash
sudo -u pulse5m /opt/pulse5m/.venv/bin/python /opt/pulse5m/bot.py --selftest
sudo -u pulse5m /opt/pulse5m/.venv/bin/python /opt/pulse5m/bot.py --check
sudo -u pulse5m /opt/pulse5m/.venv/bin/python /opt/pulse5m/bot.py --probe
```

`--check` must show `lookback=60` on all four slugs. `--probe` must print twap+raw for BTC, ETH, SOL, and XRP. If only BTC ticks, RTDS got a symbol filter — do not add filters.

### Cursor on the VPS

1. Remote-SSH into the box.
2. `git clone https://github.com/Apocalypt6/Apocalyptbot.git && cd Apocalyptbot`
3. Open that folder.
4. Paste the prompt in [`CURSOR.md`](CURSOR.md) into Cursor Agent.

Full operator notes: [`pulse5m/DEPLOY.txt`](pulse5m/DEPLOY.txt) and [`pulse5m/MATH.md`](pulse5m/MATH.md).

### What Pulse 5M actually trades

Settlement after 14 Aug 2026 is Chainlink **60s TWAP at close vs 60s TWAP at open**. Strike is the first official TWAP tick at/after the 5-minute open (lag ≤ 3s). Miss it, skip the window. Never invent a strike.

Lock (default), last 60 seconds:

```
proj = w · A + (1 − w) · spot
w    = seconds already inside [close−60, close] / 60
```

Fire only when `|proj − strike|` clears the measured residual tables. Complete-set arb runs if Up+Down asks plus fees sum to less than $1.

Live is opt-in and refused without a key in `/etc/pulse5m.env`. There is no guaranteed edge.

---

## Coinbase paper bot (legacy)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m apocalyptbot backtest --synthetic --strategy sma_crossover
```

See the original docs below the fold in git history if you need the full SMA/RSI/DCA runbook (`deploy/` at repo root).
