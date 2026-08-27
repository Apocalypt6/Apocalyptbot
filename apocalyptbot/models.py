"""Typed records parsed from Gamma / CLOB / Data API payloads."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple


def maybe_json(value: Any) -> Any:
    """Gamma often JSON-encodes arrays as strings. Pass through real lists."""
    if value is None or value == "":
        return None
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text[0] in "[{":
            try:
                return json.loads(text)
            except ValueError:
                return value
    return value


def as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Level:
    price: float
    size: float


@dataclass
class Book:
    """One CLOB book. Bids/asks are stored as returned — never trust sort order.

    Live CLOB books are *not* consistently sorted the way the docs claim.
    Always use min(ask) / max(bid).
    """

    token_id: str
    bids: List[Level] = field(default_factory=list)
    asks: List[Level] = field(default_factory=list)
    tick_size: float = 0.01
    min_order_size: float = 5.0
    last_trade_price: Optional[float] = None
    neg_risk: bool = False
    condition_id: str = ""

    @property
    def best_bid(self) -> Optional[float]:
        return max((lvl.price for lvl in self.bids), default=None)

    @property
    def best_ask(self) -> Optional[float]:
        return min((lvl.price for lvl in self.asks), default=None)

    @property
    def mid(self) -> Optional[float]:
        bid, ask = self.best_bid, self.best_ask
        if bid is None and ask is None:
            return self.last_trade_price
        if bid is None:
            return ask
        if ask is None:
            return bid
        return (bid + ask) / 2.0

    @property
    def spread(self) -> Optional[float]:
        bid, ask = self.best_bid, self.best_ask
        if bid is None or ask is None:
            return None
        return ask - bid

    def bid_size_at_or_above(self, price: float) -> float:
        return sum(lvl.size for lvl in self.bids if lvl.price >= price)

    def ask_size_at_or_below(self, price: float) -> float:
        return sum(lvl.size for lvl in self.asks if lvl.price <= price)

    @classmethod
    def from_clob(cls, payload: Dict[str, Any]) -> "Book":
        def _levels(rows: Any) -> List[Level]:
            out: List[Level] = []
            for row in rows or []:
                price = as_float(row.get("price"))
                size = as_float(row.get("size"))
                if price is None or size is None or size <= 0:
                    continue
                out.append(Level(price=price, size=size))
            return out

        return cls(
            token_id=as_str(payload.get("asset_id") or payload.get("token_id")),
            bids=_levels(payload.get("bids")),
            asks=_levels(payload.get("asks")),
            tick_size=as_float(payload.get("tick_size"), 0.01) or 0.01,
            min_order_size=as_float(payload.get("min_order_size"), 5.0) or 5.0,
            last_trade_price=as_float(payload.get("last_trade_price")),
            neg_risk=bool(payload.get("neg_risk")),
            condition_id=as_str(payload.get("market")),
        )


@dataclass
class Outcome:
    name: str
    token_id: str
    price: Optional[float] = None
    book: Optional[Book] = None


@dataclass
class Market:
    id: str
    condition_id: str
    question: str
    slug: str
    event_title: str = ""
    event_slug: str = ""
    outcomes: List[Outcome] = field(default_factory=list)
    volume_24h: float = 0.0
    liquidity: float = 0.0
    end_date: Optional[str] = None
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    spread: Optional[float] = None
    tick_size: float = 0.01
    min_order_size: float = 5.0
    neg_risk: bool = False
    fees_enabled: bool = False
    fee_type: Optional[str] = None
    accepting_orders: bool = True
    active: bool = True
    closed: bool = False
    restricted: bool = False

    @property
    def is_binary(self) -> bool:
        return len(self.outcomes) == 2

    def outcome_named(self, *names: str) -> Optional[Outcome]:
        want = {n.lower() for n in names}
        for outcome in self.outcomes:
            if outcome.name.lower() in want:
                return outcome
        return None

    @property
    def yes(self) -> Optional[Outcome]:
        return self.outcome_named("yes") or (self.outcomes[0] if self.outcomes else None)

    @property
    def no(self) -> Optional[Outcome]:
        return self.outcome_named("no") or (self.outcomes[1] if len(self.outcomes) > 1 else None)

    def hours_to_end(self, now: Optional[datetime] = None) -> Optional[float]:
        dt = parse_dt(self.end_date)
        if dt is None:
            return None
        now = now or datetime.now(timezone.utc)
        return (dt - now).total_seconds() / 3600.0

    def token_ids(self) -> List[str]:
        return [o.token_id for o in self.outcomes if o.token_id]

    @classmethod
    def from_gamma(cls, payload: Dict[str, Any], event: Optional[Dict[str, Any]] = None) -> "Market":
        event = event or {}
        if not event and payload.get("events"):
            evs = payload.get("events") or []
            if evs and isinstance(evs, list) and isinstance(evs[0], dict):
                event = evs[0]

        names = maybe_json(payload.get("outcomes")) or []
        tokens = maybe_json(payload.get("clobTokenIds")) or []
        prices = maybe_json(payload.get("outcomePrices")) or []
        outcomes: List[Outcome] = []
        for i, token in enumerate(tokens):
            name = names[i] if i < len(names) else f"outcome_{i}"
            price = as_float(prices[i]) if i < len(prices) else None
            outcomes.append(Outcome(name=str(name), token_id=str(token), price=price))

        return cls(
            id=as_str(payload.get("id")),
            condition_id=as_str(payload.get("conditionId") or payload.get("condition_id")),
            question=as_str(payload.get("question") or payload.get("title") or event.get("title")),
            slug=as_str(payload.get("slug")),
            event_title=as_str(event.get("title")),
            event_slug=as_str(event.get("slug")),
            outcomes=outcomes,
            volume_24h=as_float(payload.get("volume24hr"), 0.0) or 0.0,
            liquidity=as_float(payload.get("liquidity"), 0.0) or 0.0,
            end_date=payload.get("endDate") or payload.get("end_date") or event.get("endDate"),
            best_bid=as_float(payload.get("bestBid")),
            best_ask=as_float(payload.get("bestAsk")),
            spread=as_float(payload.get("spread")),
            tick_size=as_float(payload.get("orderPriceMinTickSize"), 0.01) or 0.01,
            min_order_size=as_float(payload.get("orderMinSize"), 5.0) or 5.0,
            neg_risk=bool(payload.get("negRisk") or payload.get("neg_risk")),
            fees_enabled=bool(payload.get("feesEnabled")),
            fee_type=payload.get("feeType") or payload.get("fee_type"),
            accepting_orders=bool(payload.get("acceptingOrders", True)),
            active=bool(payload.get("active", True)),
            closed=bool(payload.get("closed", False)),
            restricted=bool(payload.get("restricted", False)),
        )


Leg = Tuple[str, str, float, float, str]  # side, token_id, price, shares, outcome


@dataclass(frozen=True)
class Opportunity:
    kind: str
    market: Market
    edge: float
    size: float
    notional: float
    score: float
    reason: str
    legs: Tuple[Leg, ...] = ()

    def with_size(self, shares: float) -> "Opportunity":
        if shares <= 0 or self.size <= 0:
            return self
        scale = shares / self.size
        legs = tuple(
            (side, token, price, qty * scale, name) for side, token, price, qty, name in self.legs
        )
        return Opportunity(
            kind=self.kind,
            market=self.market,
            edge=self.edge,
            size=shares,
            notional=self.notional * scale,
            score=self.score,
            reason=self.reason,
            legs=legs,
        )


@dataclass(frozen=True)
class Print:
    wallet: str
    side: str
    token_id: str
    condition_id: str
    size: float
    price: float
    usd: float
    title: str
    slug: str
    outcome: str
    timestamp: int
    name: str
    tx: str

    @classmethod
    def from_api(cls, payload: Dict[str, Any]) -> "Print":
        size = as_float(payload.get("size"), 0.0) or 0.0
        price = as_float(payload.get("price"), 0.0) or 0.0
        return cls(
            wallet=as_str(payload.get("proxyWallet") or payload.get("user")),
            side=as_str(payload.get("side")).upper(),
            token_id=as_str(payload.get("asset") or payload.get("asset_id")),
            condition_id=as_str(payload.get("conditionId") or payload.get("market")),
            size=size,
            price=price,
            usd=size * price,
            title=as_str(payload.get("title")),
            slug=as_str(payload.get("slug")),
            outcome=as_str(payload.get("outcome")),
            timestamp=int(as_float(payload.get("timestamp"), 0.0) or 0),
            name=as_str(payload.get("name") or payload.get("pseudonym")),
            tx=as_str(payload.get("transactionHash")),
        )


def index_by_condition(markets: Sequence[Market]) -> Dict[str, Market]:
    return {m.condition_id: m for m in markets if m.condition_id}
