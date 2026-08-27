"""Turn live books + tape into ranked opportunities."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from .books import completeness_buy, merge_sell
from .fees import fee_rate_for
from .models import Market, Opportunity, Print


@dataclass
class HuntConfig:
    min_edge: float = 0.008
    min_shares: float = 20.0
    min_volume_24h: float = 500.0
    wide_spread: float = 0.04
    endgame_hours: float = 36.0
    endgame_prob: float = 0.92
    whale_usd: float = 2500.0
    kinds: Tuple[str, ...] = ("completeness", "merge", "wide_spread", "endgame", "whale")


def hunt(
    markets: Sequence[Market],
    prints: Optional[Sequence[Print]] = None,
    config: Optional[HuntConfig] = None,
) -> List[Opportunity]:
    cfg = config or HuntConfig()
    found: List[Opportunity] = []
    kinds = set(cfg.kinds)

    for market in markets:
        if market.closed or not market.accepting_orders:
            continue
        if market.volume_24h < cfg.min_volume_24h:
            continue
        if "completeness" in kinds or "merge" in kinds:
            found.extend(_binary_edge(market, cfg, kinds))
        if "wide_spread" in kinds:
            found.extend(_wide_spreads(market, cfg))
        if "endgame" in kinds:
            found.extend(_endgame(market, cfg))

    if prints and "whale" in kinds:
        found.extend(_whales(markets, prints, cfg))

    rank = {"completeness": 0, "merge": 1, "endgame": 2, "wide_spread": 3, "whale": 4}
    found.sort(key=lambda opp: (rank.get(opp.kind, 9), -opp.score))
    return found


def _score(edge: float, size: float, volume: float, extra: float = 1.0) -> float:
    return max(edge, 0.0) * math.log1p(size) * math.log1p(max(volume, 0.0)) * extra


def _binary_edge(market: Market, cfg: HuntConfig, kinds: set) -> List[Opportunity]:
    if not market.is_binary:
        return []
    yes, no = market.yes, market.no
    if not yes or not no or not yes.book or not no.book:
        return []
    rate = fee_rate_for(market)
    out: List[Opportunity] = []

    if "completeness" in kinds:
        raw = completeness_buy(
            yes.book, no.book, rate, min_edge=cfg.min_edge, yes_name=yes.name, no_name=no.name
        )
        if raw and raw["size"] >= cfg.min_shares:
            out.append(
                Opportunity(
                    kind="completeness",
                    market=market,
                    edge=raw["edge"],
                    size=raw["size"],
                    notional=raw["notional"],
                    score=_score(raw["edge"], raw["size"], market.volume_24h, 1.4),
                    reason=(
                        f"buy {yes.name}@{raw['yes_avg']:.4f} + {no.name}@{raw['no_avg']:.4f} "
                        f"= {raw['yes_avg'] + raw['no_avg']:.4f}  →  $1.00  "
                        f"edge {raw['edge']*100:.2f}¢/sh  fees ${raw['fees']:.4f}"
                    ),
                    legs=raw["legs"],
                )
            )

    if "merge" in kinds:
        raw = merge_sell(
            yes.book, no.book, rate, min_edge=cfg.min_edge, yes_name=yes.name, no_name=no.name
        )
        if raw and raw["size"] >= cfg.min_shares:
            out.append(
                Opportunity(
                    kind="merge",
                    market=market,
                    edge=raw["edge"],
                    size=raw["size"],
                    notional=raw["notional"],
                    score=_score(raw["edge"], raw["size"], market.volume_24h, 1.1),
                    reason=(
                        f"sell {yes.name}@{raw['yes_avg']:.4f} + {no.name}@{raw['no_avg']:.4f} "
                        f"= {raw['yes_avg'] + raw['no_avg']:.4f}  vs $1.00  "
                        f"edge {raw['edge']*100:.2f}¢/sh (needs inventory)"
                    ),
                    legs=raw["legs"],
                )
            )
    return out


def _wide_spreads(market: Market, cfg: HuntConfig) -> List[Opportunity]:
    out: List[Opportunity] = []
    for outcome in market.outcomes:
        book = outcome.book
        if not book or book.spread is None or book.best_ask is None:
            continue
        if book.spread < cfg.wide_spread:
            continue
        depth = book.ask_size_at_or_below(book.best_ask + book.spread)
        if depth < cfg.min_shares:
            continue
        out.append(
            Opportunity(
                kind="wide_spread",
                market=market,
                edge=book.spread,
                size=min(depth, 500.0),
                notional=(book.best_ask or 0) * min(depth, 500.0),
                score=_score(book.spread, depth, market.volume_24h, 0.35),
                reason=(
                    f"{outcome.name} spread {book.spread:.3f}  "
                    f"bid {book.best_bid} / ask {book.best_ask}"
                ),
                legs=(("BUY", outcome.token_id, book.best_ask, min(depth, 50.0), outcome.name),),
            )
        )
    return out


def _endgame(market: Market, cfg: HuntConfig) -> List[Opportunity]:
    hours = market.hours_to_end()
    if hours is None or hours < 0 or hours > cfg.endgame_hours:
        return []
    out: List[Opportunity] = []
    for outcome in market.outcomes:
        book = outcome.book
        mid = (book.mid if book else None) or outcome.price
        if mid is None:
            continue
        # Favorites only. A 0.1¢ long-shot is a lottery ticket, not a signal.
        if mid < cfg.endgame_prob:
            continue
        ask = book.best_ask if book else None
        if ask is None or ask >= 0.999:
            continue
        out.append(
            Opportunity(
                kind="endgame",
                market=market,
                edge=mid - 0.5,
                size=market.min_order_size,
                notional=ask * market.min_order_size,
                score=_score(mid - 0.5, 50.0, market.volume_24h, max(1.0, 12.0 / (hours + 0.5))),
                reason=(
                    f"{outcome.name} mid {mid:.3f}  ask {ask:.3f}  "
                    f"{hours:.1f}h left — favorite, still not free money"
                ),
                legs=(("BUY", outcome.token_id, ask, market.min_order_size, outcome.name),),
            )
        )
    return out


def _whales(markets: Sequence[Market], prints: Sequence[Print], cfg: HuntConfig) -> List[Opportunity]:
    by_cond = {m.condition_id: m for m in markets if m.condition_id}
    out: List[Opportunity] = []
    for print_ in prints:
        if print_.usd < cfg.whale_usd:
            continue
        market = by_cond.get(print_.condition_id)
        if market is None:
            # Synthesize a thin market so the tape still surfaces.
            market = Market(
                id="",
                condition_id=print_.condition_id,
                question=print_.title,
                slug=print_.slug,
                volume_24h=print_.usd,
            )
        out.append(
            Opportunity(
                kind="whale",
                market=market,
                edge=0.0,
                size=print_.size,
                notional=print_.usd,
                score=print_.usd,
                reason=(
                    f"{print_.name or print_.wallet[:10]} {print_.side} "
                    f"{print_.size:.0f} {print_.outcome} @ {print_.price:.3f}  "
                    f"(${print_.usd:,.0f})"
                ),
                legs=(
                    (
                        print_.side if print_.side in ("BUY", "SELL") else "BUY",
                        print_.token_id,
                        print_.price,
                        print_.size,
                        print_.outcome,
                    ),
                ),
            )
        )
    return out


def top(opps: Iterable[Opportunity], n: int = 15) -> List[Opportunity]:
    return list(opps)[:n]
