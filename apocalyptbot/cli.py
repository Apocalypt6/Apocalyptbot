"""Command-line interface.

    python -m apocalyptbot backtest --strategy sma_crossover --param fast=10 --param slow=30
    python -m apocalyptbot backtest --csv data/btc.csv --strategy rsi
    python -m apocalyptbot fetch --symbol BTC-USD --interval 1h --out data/btc.csv
    python -m apocalyptbot paper --strategy dca --param every=24 --param amount=100 --once
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import Any, Dict, List

from . import __version__, strategies
from .backtest import run_backtest
from .broker import PaperBroker
from .config import Config
from .data import CoinbaseData, DataError, load_csv, save_csv, synthetic
from .engine import TradingEngine
from .notify import Notifier
from .portfolio import Portfolio

_PERIODS_PER_YEAR = {"1m": 525600, "5m": 105120, "15m": 35040, "1h": 8760, "6h": 1460, "1d": 365}


def _parse_params(pairs: List[str]) -> Dict[str, Any]:
    """Turn ['fast=10', 'amount=100.5'] into {'fast': 10, 'amount': 100.5}."""
    out: Dict[str, Any] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"bad --param {pair!r}; expected key=value")
        key, raw = pair.split("=", 1)
        out[key.strip()] = _coerce(raw.strip())
    return out


def _coerce(value: str) -> Any:
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            continue
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"
    return value


def _load_candles(args) -> list:
    if args.csv:
        return load_csv(args.csv)
    if getattr(args, "synthetic", False):
        return synthetic(n=args.synthetic_bars)
    client = CoinbaseData()
    return client.candles(args.symbol, interval=args.interval, limit=args.limit)


def cmd_fetch(args) -> int:
    try:
        candles = CoinbaseData().candles(args.symbol, interval=args.interval, limit=args.limit)
    except DataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    save_csv(candles, args.out)
    print(f"saved {len(candles)} candles to {args.out}")
    return 0


def cmd_backtest(args) -> int:
    try:
        candles = _load_candles(args)
    except DataError as exc:
        print(f"error fetching data: {exc}", file=sys.stderr)
        print("tip: use --synthetic for an offline demo, or --csv <file>", file=sys.stderr)
        return 1
    if len(candles) < 2:
        print("error: not enough candles", file=sys.stderr)
        return 1

    params = _parse_params(args.param)
    try:
        strategy = strategies.build(args.strategy, **params)
    except (ValueError, TypeError) as exc:
        print(f"error building strategy: {exc}", file=sys.stderr)
        return 1

    result = run_backtest(
        candles,
        strategy,
        symbol=args.symbol,
        starting_cash=args.cash,
        fee_rate=args.fee,
        slippage=args.slippage,
        periods_per_year=_PERIODS_PER_YEAR.get(args.interval, 8760),
    )
    print(result.summary())
    return 0


def cmd_paper(args) -> int:
    params = _parse_params(args.param)
    try:
        strategy = strategies.build(args.strategy, **params)
    except (ValueError, TypeError) as exc:
        print(f"error building strategy: {exc}", file=sys.stderr)
        return 1

    portfolio = Portfolio(cash=args.cash)
    broker = PaperBroker(portfolio, fee_rate=args.fee, slippage=args.slippage)
    client = CoinbaseData()

    def fetch():
        return client.candles(args.symbol, interval=args.interval, limit=args.limit)

    notifier = Notifier.from_env()
    if notifier.enabled:
        logging.getLogger("apocalyptbot").info("notifications enabled")
    engine = TradingEngine(
        fetch,
        strategy,
        broker,
        symbol=args.symbol,
        state_path=args.state,
        notifier=notifier,
        heartbeat_path=args.heartbeat,
    )
    if not args.fresh:
        engine.load_state()

    if args.once:
        engine.step()
    else:
        engine.run(poll_seconds=args.poll, max_iterations=args.iterations)
    return 0


def cmd_health(args) -> int:
    """Exit 0 if the heartbeat file is fresh, non-zero otherwise (for healthchecks)."""
    path = args.heartbeat
    if not os.path.exists(path):
        print(f"unhealthy: no heartbeat file at {path}", file=sys.stderr)
        return 1
    try:
        with open(path) as fh:
            ts = int(fh.read().strip())
    except (ValueError, OSError) as exc:
        print(f"unhealthy: cannot read heartbeat: {exc}", file=sys.stderr)
        return 1
    age = time.time() - ts
    if age > args.max_age:
        print(f"unhealthy: heartbeat is {age:.0f}s old (max {args.max_age}s)", file=sys.stderr)
        return 1
    print(f"healthy: heartbeat is {age:.0f}s old")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="apocalyptbot", description="A small, honest crypto paper-trading & backtesting bot.")
    p.add_argument("--version", action="version", version=f"apocalyptbot {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="enable debug logging")
    sub = p.add_subparsers(dest="command", required=True)

    # Shared options
    def add_common(sp):
        sp.add_argument("--symbol", default="BTC-USD", help="trading pair, e.g. BTC-USD")
        sp.add_argument("--interval", default="1h", choices=list(_PERIODS_PER_YEAR), help="candle interval")
        sp.add_argument("--limit", type=int, default=300, help="max candles to fetch")

    sp_fetch = sub.add_parser("fetch", help="download candles to a CSV file")
    add_common(sp_fetch)
    sp_fetch.add_argument("--out", default="data/candles.csv", help="output CSV path")
    sp_fetch.set_defaults(func=cmd_fetch)

    sp_bt = sub.add_parser("backtest", help="backtest a strategy over historical data")
    add_common(sp_bt)
    sp_bt.add_argument("--strategy", default="sma_crossover", choices=sorted(strategies.REGISTRY))
    sp_bt.add_argument("--param", action="append", default=[], help="strategy param key=value (repeatable)")
    sp_bt.add_argument("--csv", help="load candles from CSV instead of the network")
    sp_bt.add_argument("--synthetic", action="store_true", help="use generated demo data (offline)")
    sp_bt.add_argument("--synthetic-bars", type=int, default=500)
    sp_bt.add_argument("--cash", type=float, default=10_000.0)
    sp_bt.add_argument("--fee", type=float, default=0.005, help="taker fee rate (0.005 = 0.5%%)")
    sp_bt.add_argument("--slippage", type=float, default=0.0005)
    sp_bt.set_defaults(func=cmd_backtest)

    sp_paper = sub.add_parser("paper", help="run live paper trading (simulated money)")
    add_common(sp_paper)
    sp_paper.add_argument("--strategy", default="sma_crossover", choices=sorted(strategies.REGISTRY))
    sp_paper.add_argument("--param", action="append", default=[], help="strategy param key=value (repeatable)")
    sp_paper.add_argument("--cash", type=float, default=10_000.0)
    sp_paper.add_argument("--fee", type=float, default=0.005)
    sp_paper.add_argument("--slippage", type=float, default=0.0005)
    sp_paper.add_argument("--poll", type=float, default=3600.0, help="seconds between cycles")
    sp_paper.add_argument("--iterations", type=int, default=None, help="stop after N cycles")
    sp_paper.add_argument("--once", action="store_true", help="run a single cycle and exit")
    sp_paper.add_argument("--state", default="state/portfolio.state.json", help="portfolio state file")
    sp_paper.add_argument("--heartbeat", default="state/heartbeat", help="heartbeat file for healthchecks")
    sp_paper.add_argument("--fresh", action="store_true", help="ignore any saved state")
    sp_paper.set_defaults(func=cmd_paper)

    sp_health = sub.add_parser("health", help="check the bot's heartbeat freshness (for monitoring)")
    sp_health.add_argument("--heartbeat", default="state/heartbeat", help="heartbeat file to check")
    sp_health.add_argument("--max-age", type=float, default=900.0, help="max heartbeat age in seconds")
    sp_health.set_defaults(func=cmd_health)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
