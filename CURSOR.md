# Cursor — finish Pulse 5M on this VPS

You are on the operator's Ubuntu VPS with this repo already cloned (or clone it):

```
git clone https://github.com/Apocalypt6/Apocalyptbot.git
cd Apocalyptbot
```

The Polymarket worker is in `pulse5m/`. Do the work on this machine. Do not ask the operator to run commands you can run yourself.

## Goal

- Install Pulse 5M as systemd in **paper** mode.
- Prove feeds with `--check` and `--probe`.
- Leave it running on `:8080/health`.
- Do **not** enable live trading. Do **not** ask for, write, or echo a private key.

## Rules that already exist in `pulse5m/`

- Markets: `{asset}-updown-5m-{unix}` where `unix = floor(t/300)*300`.
- Settlement: Chainlink 60s TWAP at close vs 60s TWAP at open. Gamma `twapLookbackSeconds` must be 60.
- Strike = first official RTDS `crypto_prices_twap_sixty` tick at/after window open, lag ≤ 3s. Miss it → skip. Never invent a strike from Binance / Coinbase / last trade.
- Lock: `proj = w*A + (1-w)*spot` over `[close-60, close]`. Fire only if `|proj-strike|` clears tables in `pulse5m/strategy.py`.
- Official TWAP and raw proj must agree on side after 40s into the horizon; if they agree, use the smaller displacement.
- RTDS subscribe is **unfiltered**. Filter symbols client-side.
- Last 70s is event-driven (raw Chainlink tick or CLOB market WS). Do not rip `clob_ws.py` out.
- Forbidden: mid-window tanh, martingale, underdog buys (`min_ask` stays 0.50).

## Steps

1. `cd pulse5m` and confirm `bot.py`, `strategy.py`, `rtds.py`, `clob_ws.py`, `deploy.sh`, `install.sh` exist.
2. Install and enable chrony. `timedatectl` should show NTP synchronized. A 2-second clock error is a wrong window.
3. `sudo bash deploy.sh`
4. Run and keep the outputs:

```
curl -s http://127.0.0.1:8080/health
sudo -u pulse5m /opt/pulse5m/.venv/bin/python /opt/pulse5m/bot.py --selftest
sudo -u pulse5m /opt/pulse5m/.venv/bin/python /opt/pulse5m/bot.py --check
sudo -u pulse5m /opt/pulse5m/.venv/bin/python /opt/pulse5m/bot.py --probe
journalctl -u pulse5m -n 50 --no-pager
```

`--check` must list btc/eth/sol/xrp with `lookback=60`.
`--probe` must stream twap+raw for **all four**. If only BTC ticks, remove any symbol filter from `rtds.py`, restart, probe again.

5. Print health JSON, lookbacks, whether probe saw 4 assets, and the watch commands. Do not set `PULSE_MODE=live`.

## Watch

```
journalctl -u pulse5m -f
tail -f /var/lib/pulse5m/journal.jsonl
curl -s localhost:8080/health
```
