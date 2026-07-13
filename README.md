# Apocalyptbot

A small, honest crypto trading bot. It **paper-trades** (simulated money) and
**backtests** pluggable strategies against public market data, so you can test
ideas safely before risking a single real dollar.

> **Read this first.** A bot does not "make money" on its own — it automates a
> strategy you'd otherwise run by hand. Whether it wins or loses comes down to
> the strategy, and most simple strategies barely beat buy-and-hold after fees.
> This tool is built to help you *find that out cheaply*, in simulation, rather
> than learn it with real money. Nothing here is financial advice, and no
> strategy is guaranteed to be profitable. **Never trade money you can't afford
> to lose.**

## What it does today

- **Backtesting** — replay a strategy over historical candles with no
  lookahead, and score it: return, max drawdown, rough Sharpe, trade count,
  win rate, fees paid, and a **buy-and-hold** comparison.
- **Paper trading** — run the same strategy live against real prices with
  simulated cash; state is saved to disk so you can stop and resume.
- **Public data** — Coinbase's public API (no account or API key needed), plus
  offline CSV and a deterministic synthetic generator for demos/tests.
- **Three strategies out of the box** — DCA, SMA crossover, RSI mean-reversion.

It does **not** place real orders yet. Live trading is a deliberate, separate
step (see [Roadmap](#roadmap)).

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# or: pip install -e ".[dev]"
```

Requires Python 3.9+.

## Quick start

Everything runs through `python -m apocalyptbot` (or the `apocalyptbot` command
if installed).

**Backtest offline right now — no network needed:**

```bash
python -m apocalyptbot backtest --synthetic --strategy sma_crossover \
    --param fast=10 --param slow=30
```

**Backtest on real recent BTC data:**

```bash
python -m apocalyptbot backtest --symbol BTC-USD --interval 1h \
    --strategy rsi --param period=14 --param oversold=30 --param overbought=70
```

**Download candles to a CSV, then backtest against the file:**

```bash
python -m apocalyptbot fetch --symbol ETH-USD --interval 1d --out data/eth.csv
python -m apocalyptbot backtest --csv data/eth.csv --strategy dca \
    --param every=7 --param amount=50
```

**Paper trade (simulated money, live prices):**

```bash
# one cycle and exit (good for testing / cron)
python -m apocalyptbot paper --strategy sma_crossover --once

# continuous loop, one decision per hour
python -m apocalyptbot paper --strategy sma_crossover --poll 3600
```

Sample backtest output:

```
Backtest: sma_crossover on BTC-USD
  Bars tested:      270
  Starting cash:    10,000.00
  Final equity:     10,842.31
  Strategy return:  +8.42%
  Buy & hold:       +11.90%      <- did the strategy beat just holding?
  Max drawdown:     14.20%
  Sharpe (rough):   0.71
  Trades:           8
  Win rate:         50.0%
  Fees paid:        63.40
```

Always read `Strategy return` **against** `Buy & hold`. Beating a rising market
is much harder than it looks.

## Strategies

| Name            | Idea                                              | Key params |
|-----------------|---------------------------------------------------|------------|
| `dca`           | Buy a fixed amount every N candles                | `every`, `amount` |
| `sma_crossover` | Long when fast SMA crosses above slow, exit below | `fast`, `slow`, `allocation` |
| `rsi`           | Buy oversold (RSI low), sell overbought (RSI high)| `period`, `oversold`, `overbought`, `allocation` |

Pass parameters with repeated `--param key=value` flags.

### Writing your own

Subclass `Strategy` and implement `decide()`. It's a pure function — given the
candles so far and the current portfolio, return a `Decision` (BUY/SELL/HOLD
plus a size). No broker access, which is what makes it safe to backtest.

```python
from apocalyptbot.strategies.base import Strategy, Decision
from apocalyptbot.data import closes

class BuyTheDip(Strategy):
    name = "buy_the_dip"
    def decide(self, symbol, candles, portfolio):
        prices = closes(candles)
        if len(prices) < 2:
            return Decision.hold()
        if prices[-1] < prices[-2] * 0.95:      # down 5% on the bar
            return Decision.buy(0.25, "bought the dip")
        return Decision.hold()
```

Register it in `apocalyptbot/strategies/__init__.py` and it's usable from the CLI.

## How the simulation stays honest

- **No lookahead.** At bar *i* the strategy only sees candles `[0..i]`.
- **Fees and slippage on every fill**, charged *against* you, so paper results
  aren't rosier than live.
- **Marked-to-market equity** at each bar for the drawdown/Sharpe curve.

These are simplifications, not a market simulator — real fills, partial fills,
latency, and liquidity are not modeled. Treat backtest numbers as a filter for
bad ideas, not a promise of returns.

## Project layout

```
apocalyptbot/
  data.py           # Coinbase client, CSV load/save, synthetic generator
  indicators.py     # SMA / EMA / RSI / crossovers (pure, dependency-free)
  portfolio.py      # cash + positions accounting
  broker.py         # PaperBroker: fees, slippage, fills, realized PnL
  strategies/       # base interface + dca / sma_crossover / rsi + registry
  backtest.py       # walk-forward backtester + metrics
  engine.py         # live/paper poll-decide-execute loop, state persistence
  cli.py            # `python -m apocalyptbot ...`
tests/              # pytest suite (offline; no network required)
```

## Security & going live

- **API keys are never stored in the repo.** Config files carry no secrets;
  if/when live trading lands, keys are read from `APOCALYPTBOT_API_KEY` /
  `APOCALYPTBOT_API_SECRET` environment variables only. `.env`, `config.json`,
  and state files are gitignored.
- Before any real trading you'd want, at minimum: exchange keys scoped to
  **trade-only, no withdrawal**, hard position/loss limits, and a long
  paper-trading run first.

## Roadmap

- [ ] Live broker adapters (Coinbase Advanced Trade, Kraken) behind the same
      `buy`/`sell` interface the paper broker already uses
- [ ] Risk controls: stop-loss, take-profit, max position size, daily loss cap
- [ ] Parameter sweeps / walk-forward optimization
- [ ] More strategies (grid, Bollinger bands, MACD) and multi-asset portfolios
- [ ] Equity-curve plotting and an HTML report

## Tests

```bash
pip install -e ".[dev]"
pytest
```

The suite is fully offline (synthetic data), so it runs anywhere.

## Disclaimer

This software is for education and research. It is not financial advice.
Cryptocurrency trading carries substantial risk of loss. You are solely
responsible for any use of this code and any money you choose to put at risk.
