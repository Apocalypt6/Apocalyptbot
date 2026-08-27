"""Command line for the Polymarket hunter."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List

from . import __version__, strategies
from .broker import LiveBroker, PaperBroker
from .clob import Clob
from .display import edge_cents, money, paint, px, table, truncate
from .engine import Engine
from .gamma import Gamma
from .hunt import HuntConfig, hunt
from .models import Market, Opportunity
from .notify import Notifier
from .portfolio import Portfolio
from .research import ResearchDisabled, estimate_exa_cost, run_research
from .risk import RiskGate, RiskLimits
from .tape import Tape


def _params(pairs: List[str]) -> Dict[str, Any]:
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


def _clients():
    return Gamma(), Clob(), Tape()


def _hunt_config(args) -> HuntConfig:
    kinds = tuple(k.strip() for k in (getattr(args, "kinds", "") or "").split(",") if k.strip())
    cfg = HuntConfig(
        min_edge=getattr(args, "min_edge", 0.008),
        min_shares=getattr(args, "min_shares", 20.0),
        min_volume_24h=getattr(args, "min_volume", 500.0),
        whale_usd=getattr(args, "min_usd", 2500.0),
    )
    if kinds:
        cfg.kinds = kinds
    return cfg


def _load_universe(gamma: Gamma, clob: Clob, args) -> List[Market]:
    query = getattr(args, "query", None)
    slug = getattr(args, "slug", None)
    if slug:
        raw = gamma.market_by_slug(slug)
        markets = [Market.from_gamma(raw)]
    elif query:
        payload = gamma.search(query, limit_per_type=getattr(args, "limit", 20))
        markets = []
        for event in payload.get("events") or []:
            for raw in event.get("markets") or []:
                markets.append(Market.from_gamma(raw, event))
        if not markets:
            for raw in gamma.markets(limit=getattr(args, "limit", 20)):
                market = Market.from_gamma(raw)
                if query.lower() in (market.question + market.slug).lower():
                    markets.append(market)
    else:
        markets = gamma.hot_markets(limit=getattr(args, "limit", 40))
    return clob.attach_books(markets)


def _print_markets(markets: List[Market], json_mode: bool) -> None:
    if json_mode:
        print(json.dumps([_market_json(m) for m in markets], indent=2))
        return
    rows = []
    for i, m in enumerate(markets, 1):
        yes, no = m.yes, m.no
        y = (yes.book.mid if yes and yes.book and yes.book.mid is not None else (yes.price if yes else None))
        n = (no.book.mid if no and no.book and no.book.mid is not None else (no.price if no else None))
        spr = None
        if yes and yes.book:
            spr = yes.book.spread
        elif m.spread is not None:
            spr = m.spread
        rows.append(
            (
                str(i),
                truncate(m.question, 54),
                px(y),
                px(n),
                px(spr),
                money(m.volume_24h),
                money(m.liquidity),
            )
        )
    print(table((" #", "MARKET", "YES", "NO", "SPRD", "VOL24H", "LIQ"), rows, aligns=["right", "left", "right", "right", "right", "right", "right"]))
    print(paint(f"{len(markets)} markets  ·  free Gamma + CLOB reads", "dim"))


def _market_json(m: Market) -> dict:
    return {
        "question": m.question,
        "slug": m.slug,
        "condition_id": m.condition_id,
        "volume_24h": m.volume_24h,
        "liquidity": m.liquidity,
        "end_date": m.end_date,
        "fee_type": m.fee_type,
        "fees_enabled": m.fees_enabled,
        "outcomes": [
            {
                "name": o.name,
                "token_id": o.token_id,
                "price": o.price,
                "best_bid": o.book.best_bid if o.book else None,
                "best_ask": o.book.best_ask if o.book else None,
                "spread": o.book.spread if o.book else None,
            }
            for o in m.outcomes
        ],
    }


def _print_opps(opps: List[Opportunity], json_mode: bool) -> None:
    if json_mode:
        print(
            json.dumps(
                [
                    {
                        "kind": o.kind,
                        "edge": o.edge,
                        "size": o.size,
                        "notional": o.notional,
                        "score": o.score,
                        "reason": o.reason,
                        "question": o.market.question,
                        "slug": o.market.slug,
                    }
                    for o in opps
                ],
                indent=2,
            )
        )
        return
    if not opps:
        print(paint("no opportunities over the current thresholds", "dim"))
        return
    rows = []
    for i, o in enumerate(opps, 1):
        rows.append(
            (
                str(i),
                o.kind,
                truncate(o.market.question, 44),
                edge_cents(o.edge, o.kind),
                f"{o.size:.0f}",
                money(o.notional, 0),
            )
        )
    print(table(("#", "KIND", "MARKET", "EDGE", "SH", "$"), rows, aligns=["right", "left", "left", "right", "right", "right"]))
    print()
    for i, o in enumerate(opps[:8], 1):
        print(paint(f"  {i}. ", "dim") + o.reason)


def cmd_scan(args) -> int:
    gamma, clob, _tape = _clients()
    try:
        markets = _load_universe(gamma, clob, args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    _print_markets(markets, args.json)
    return 0


def cmd_hunt(args) -> int:
    gamma, clob, tape = _clients()
    cfg = _hunt_config(args)

    def once() -> int:
        try:
            markets = _load_universe(gamma, clob, args)
            prints = tape.trades(limit=80, min_usd=cfg.whale_usd) if "whale" in cfg.kinds else []
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        opps = hunt(markets, prints=prints, config=cfg)
        if not args.json:
            print(paint(f"hunted {len(markets)} books  ·  {len(opps)} opportunities", "dim"))
        _print_opps(opps[: args.top], args.json)
        return 0

    if not args.watch:
        return once()
    n = 0
    while True:
        if not args.json:
            print(paint(time.strftime("\n%H:%M:%S  hunt cycle"), "cyan"))
        rc = once()
        if rc:
            return rc
        n += 1
        if args.iterations and n >= args.iterations:
            return 0
        time.sleep(args.poll)


def cmd_tape(args) -> int:
    _g, _c, tape = _clients()
    try:
        prints = tape.trades(limit=args.limit, min_usd=args.min_usd, user=args.user, market=args.market)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps([p.__dict__ for p in prints], indent=2))
        return 0
    rows = [
        (
            p.side,
            money(p.usd),
            f"{p.size:.0f}@{px(p.price)}",
            truncate(p.outcome, 12),
            truncate(p.title, 40),
            truncate(p.name or p.wallet, 16),
        )
        for p in prints
    ]
    print(table(("SIDE", "USD", "FILL", "OUT", "MARKET", "WHO"), rows, aligns=["left", "right", "right", "left", "left", "left"]))
    return 0


def cmd_whale(args) -> int:
    _g, _c, tape = _clients()
    addr = args.address
    try:
        positions = tape.positions(addr)
        prints = tape.trades(user=addr, limit=args.limit)
        value = tape.value(addr)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"value": value, "positions": positions, "trades": [p.__dict__ for p in prints]}, indent=2, default=str))
        return 0
    print(paint(f"wallet {addr}", "bold"))
    print(f"value endpoint: {value}")
    rows = []
    for pos in positions[:40]:
        rows.append(
            (
                truncate(str(pos.get("title") or pos.get("slug") or ""), 40),
                str(pos.get("outcome") or ""),
                f"{float(pos.get('size') or 0):.1f}",
                px(float(pos.get("avgPrice") or pos.get("avg_price") or 0) or None),
                money(float(pos.get("currentValue") or pos.get("current_value") or 0), 0),
            )
        )
    if rows:
        print(table(("MARKET", "OUT", "SH", "AVG", "VAL"), rows, aligns=["left", "left", "right", "right", "right"]))
    else:
        print(paint("no positions", "dim"))
    print()
    print(paint("recent tape", "bold"))
    cmd_args = argparse.Namespace(json=False, limit=args.limit, min_usd=0, user=addr, market=None)
    # reprint from already-fetched prints
    rows = [
        (p.side, money(p.usd), f"{p.size:.0f}@{px(p.price)}", truncate(p.title, 44))
        for p in prints
    ]
    if rows:
        print(table(("SIDE", "USD", "FILL", "MARKET"), rows))
    _ = cmd_args
    return 0


def cmd_market(args) -> int:
    gamma, clob, tape = _clients()
    try:
        raw = gamma.market_by_slug(args.slug)
        market = Market.from_gamma(raw)
        clob.attach_books([market])
        prints = tape.trades(market=market.condition_id, limit=15) if market.condition_id else []
        holders = tape.holders(market.condition_id) if market.condition_id else []
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"market": _market_json(market), "tape": [p.__dict__ for p in prints], "holders": holders}, indent=2, default=str))
        return 0
    print(paint(market.question, "bold"))
    print(paint(f"slug {market.slug}  condition {market.condition_id}", "dim"))
    print(
        f"vol24h {money(market.volume_24h)}  liq {money(market.liquidity)}  "
        f"fees {market.fee_type or 'off'}  tick {market.tick_size}  "
        f"end {market.end_date or '—'}"
    )
    rows = []
    for o in market.outcomes:
        b = o.book
        rows.append(
            (
                o.name,
                px(o.price),
                px(b.best_bid if b else None),
                px(b.best_ask if b else None),
                px(b.spread if b else None),
                f"{b.bid_size_at_or_above(b.best_bid) if b and b.best_bid else 0:.0f}",
                f"{b.ask_size_at_or_below(b.best_ask) if b and b.best_ask else 0:.0f}",
            )
        )
    print(table(("OUTCOME", "MARK", "BID", "ASK", "SPRD", "BID SZ", "ASK SZ"), rows, aligns=["left"] + ["right"] * 6))
    opps = hunt([market], prints=prints, config=_hunt_config(args))
    print()
    _print_opps(opps, False)
    return 0


def _make_engine(args, live: bool = False) -> Engine:
    gamma, clob, tape = _clients()
    params = _params(getattr(args, "param", None) or [])
    strategy = strategies.build(args.strategy, **params)
    portfolio = Portfolio(cash=args.cash)
    if live:
        broker = LiveBroker(portfolio=portfolio, confirmed=bool(args.i_understand_this_risks_real_money))
    else:
        broker = PaperBroker(portfolio, slippage=getattr(args, "slippage", 0.0))
    risk = RiskGate(
        RiskLimits(
            max_notional_per_trade=args.max_notional,
            max_total_exposure=args.max_exposure,
            max_daily_loss=args.max_daily_loss,
            min_edge=args.min_edge,
        )
    )
    engine = Engine(
        gamma,
        clob,
        tape,
        strategy,
        broker,
        risk=risk,
        state_path=args.state,
        heartbeat_path=args.heartbeat,
        notifier=Notifier.from_env(),
        hunt_limit=args.limit,
        hunt_config=_hunt_config(args),
    )
    if not args.fresh:
        engine.load_state()
    return engine


def cmd_paper(args) -> int:
    engine = _make_engine(args, live=False)
    if args.once:
        fills = engine.step()
        picked = [o for o in engine.last_opportunities if o.kind in ("completeness", "merge")]
        if engine.strategy.name != "completeness":
            picked = engine.last_opportunities[: args.top]
        if args.json:
            _print_opps(engine.last_opportunities[: args.top], True)
        else:
            print(paint(f"strategy {engine.strategy.name}: {engine.last_reason}", "dim"))
            _print_opps(picked[: args.top], False)
            print(paint(f"paper fills: {len(fills)}  cash {engine.portfolio.cash:.2f}", "green" if fills else "dim"))
        return 0
    engine.run(poll_seconds=args.poll, max_iterations=args.iterations)
    return 0


def cmd_live(args) -> int:
    if not args.i_understand_this_risks_real_money:
        print(
            "live trading is off. Re-run with --i-understand-this-risks-real-money "
            "and POLYMARKET_PRIVATE_KEY if you actually want CLOB V2 orders.",
            file=sys.stderr,
        )
        return 2
    if not os.environ.get("POLYMARKET_PRIVATE_KEY"):
        print("live trading refused: POLYMARKET_PRIVATE_KEY is empty", file=sys.stderr)
        return 2
    engine = _make_engine(args, live=True)
    if args.once:
        engine.step()
        return 0
    engine.run(poll_seconds=args.poll, max_iterations=args.iterations)
    return 0


def cmd_health(args) -> int:
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


def cmd_research(args) -> int:
    print(
        paint(
            f"paid search is not on the hunt path. Instant search ≈ ${estimate_exa_cost(1):.3f} each.",
            "yellow",
        )
    )
    try:
        run_research(args.query, budget_usd=args.budget)
    except ResearchDisabled as exc:
        print(exc)
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="apocalyptbot",
        description="Polymarket hunter — scan books, hunt completeness, paper-trade. Not financial advice.",
    )
    p.add_argument("--version", action="version", version=f"apocalyptbot {__version__}")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    def add_json(sp):
        sp.add_argument("--json", action="store_true", help="machine-readable output")

    def add_universe(sp):
        sp.add_argument("--limit", type=int, default=40, help="how many hot markets to pull")
        sp.add_argument("--query", help="search Gamma instead of the volume leaderboard")
        sp.add_argument("--slug", help="pin to one market slug")

    def add_hunt_flags(sp):
        sp.add_argument("--min-edge", type=float, default=0.008)
        sp.add_argument("--min-shares", type=float, default=20.0)
        sp.add_argument("--min-volume", type=float, default=500.0)
        sp.add_argument("--min-usd", type=float, default=2500.0, help="whale print floor")
        sp.add_argument("--kinds", default="", help="comma list: completeness,merge,wide_spread,endgame,whale")
        sp.add_argument("--top", type=int, default=15)

    sp = sub.add_parser("scan", help="hottest markets")
    add_universe(sp)
    add_json(sp)
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("hunt", help="score completeness / merge / tape / endgame")
    add_universe(sp)
    add_hunt_flags(sp)
    add_json(sp)
    sp.add_argument("--watch", action="store_true")
    sp.add_argument("--poll", type=float, default=30.0)
    sp.add_argument("--iterations", type=int, default=None)
    sp.set_defaults(func=cmd_hunt)

    sp = sub.add_parser("tape", help="large prints")
    add_json(sp)
    sp.add_argument("--limit", type=int, default=30)
    sp.add_argument("--min-usd", type=float, default=1000.0)
    sp.add_argument("--user", default=None)
    sp.add_argument("--market", default=None, help="condition id")
    sp.set_defaults(func=cmd_tape)

    sp = sub.add_parser("whale", help="one wallet's positions + tape")
    add_json(sp)
    sp.add_argument("address")
    sp.add_argument("--limit", type=int, default=25)
    sp.set_defaults(func=cmd_whale)

    sp = sub.add_parser("market", help="deep dive a slug")
    add_json(sp)
    add_hunt_flags(sp)
    sp.add_argument("slug")
    sp.set_defaults(func=cmd_market)

    def add_engine(sp):
        add_universe(sp)
        add_hunt_flags(sp)
        add_json(sp)
        sp.add_argument("--strategy", default="completeness", choices=sorted(strategies.REGISTRY))
        sp.add_argument("--param", action="append", default=[], help="strategy param key=value")
        sp.add_argument("--cash", type=float, default=1000.0)
        sp.add_argument("--slippage", type=float, default=0.0)
        sp.add_argument("--max-notional", type=float, default=50.0)
        sp.add_argument("--max-exposure", type=float, default=500.0)
        sp.add_argument("--max-daily-loss", type=float, default=75.0)
        sp.add_argument("--poll", type=float, default=30.0)
        sp.add_argument("--iterations", type=int, default=None)
        sp.add_argument("--once", action="store_true")
        sp.add_argument("--state", default="state/portfolio.state.json")
        sp.add_argument("--heartbeat", default="state/heartbeat")
        sp.add_argument("--fresh", action="store_true")

    sp = sub.add_parser("paper", help="simulated money against live books")
    add_engine(sp)
    sp.set_defaults(func=cmd_paper)

    sp = sub.add_parser("live", help="real CLOB V2 orders — refused without the risk flag")
    add_engine(sp)
    sp.add_argument(
        "--i-understand-this-risks-real-money",
        action="store_true",
        help="required. Live orders spend pUSD.",
    )
    sp.set_defaults(func=cmd_live)

    sp = sub.add_parser("health", help="heartbeat freshness")
    sp.add_argument("--heartbeat", default="state/heartbeat")
    sp.add_argument("--max-age", type=float, default=900.0)
    sp.set_defaults(func=cmd_health)

    sp = sub.add_parser("research", help="paid web search — disabled on purpose")
    sp.add_argument("query")
    sp.add_argument("--budget", type=float, default=0.0, help="USD cap; 0 refuses")
    sp.set_defaults(func=cmd_research)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
