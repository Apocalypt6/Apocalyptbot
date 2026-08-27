"""Shared offline fixtures. No network — every book/market is constructed in-process."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Iterable, List, Optional, Sequence, Tuple

import pytest

from apocalyptbot.models import Book, Level, Market, Opportunity, Outcome, Print
from apocalyptbot.portfolio import Portfolio


# ---------------------------------------------------------------------------
# Factories (imported by test modules; also wrapped as fixtures below)
# ---------------------------------------------------------------------------


def make_book(
    token_id: str,
    bids: Sequence[Tuple[float, float]] = (),
    asks: Sequence[Tuple[float, float]] = (),
    **kwargs,
) -> Book:
    return Book(
        token_id=token_id,
        bids=[Level(price, size) for price, size in bids],
        asks=[Level(price, size) for price, size in asks],
        **kwargs,
    )


def make_binary_market(
    *,
    yes_ask: float = 0.40,
    no_ask: float = 0.55,
    yes_bid: float = 0.39,
    no_bid: float = 0.54,
    ask_yes_size: float = 100.0,
    ask_no_size: float = 80.0,
    bid_yes_size: float = 50.0,
    bid_no_size: float = 50.0,
    volume_24h: float = 10_000.0,
    fees_enabled: bool = False,
    fee_type: Optional[str] = None,
    closed: bool = False,
    accepting_orders: bool = True,
    condition_id: str = "0xcondition",
    slug: str = "will-x-happen",
    question: str = "Will X happen?",
    min_order_size: float = 5.0,
    yes_name: str = "Yes",
    no_name: str = "No",
    yes_token: str = "tok-yes",
    no_token: str = "tok-no",
    end_date: Optional[str] = None,
) -> Market:
    yes_book = make_book(
        yes_token,
        bids=[(yes_bid, bid_yes_size)],
        asks=[(yes_ask, ask_yes_size)],
    )
    no_book = make_book(
        no_token,
        bids=[(no_bid, bid_no_size)],
        asks=[(no_ask, ask_no_size)],
    )
    return Market(
        id="m1",
        condition_id=condition_id,
        question=question,
        slug=slug,
        outcomes=[
            Outcome(name=yes_name, token_id=yes_token, price=yes_ask, book=yes_book),
            Outcome(name=no_name, token_id=no_token, price=no_ask, book=no_book),
        ],
        volume_24h=volume_24h,
        accepting_orders=accepting_orders,
        closed=closed,
        fees_enabled=fees_enabled,
        fee_type=fee_type,
        min_order_size=min_order_size,
        end_date=end_date,
    )


def make_opportunity(
    market: Market,
    *,
    kind: str = "completeness",
    edge: float = 0.05,
    size: float = 80.0,
    yes_px: float = 0.40,
    no_px: float = 0.55,
    side: str = "BUY",
    score: float = 1.0,
    reason: str = "test opportunity",
) -> Opportunity:
    yes, no = market.yes, market.no
    notional = (yes_px + no_px) * size
    return Opportunity(
        kind=kind,
        market=market,
        edge=edge,
        size=size,
        notional=notional,
        score=score,
        reason=reason,
        legs=(
            (side, yes.token_id, yes_px, size, yes.name),
            (side, no.token_id, no_px, size, no.name),
        ),
    )


def make_print(
    *,
    wallet: str = "0xabc",
    side: str = "BUY",
    token_id: str = "tok-yes",
    condition_id: str = "0xcondition",
    size: float = 10_000.0,
    price: float = 0.50,
    usd: Optional[float] = None,
    title: str = "Will X happen?",
    slug: str = "will-x-happen",
    outcome: str = "Yes",
    timestamp: int = 1_700_000_000,
    name: str = "whale-1",
    tx: str = "0xtx",
) -> Print:
    return Print(
        wallet=wallet,
        side=side,
        token_id=token_id,
        condition_id=condition_id,
        size=size,
        price=price,
        usd=size * price if usd is None else usd,
        title=title,
        slug=slug,
        outcome=outcome,
        timestamp=timestamp,
        name=name,
        tx=tx,
    )


def make_gamma_payload(**overrides) -> dict:
    payload = {
        "id": "42",
        "conditionId": "0xcondition",
        "question": "Will X happen?",
        "slug": "will-x-happen",
        "outcomes": '["Yes", "No"]',
        "clobTokenIds": '["tok-yes", "tok-no"]',
        "outcomePrices": '["0.40", "0.60"]',
        "volume24hr": "10000",
        "liquidity": "2500",
        "feesEnabled": True,
        "feeType": "crypto_fees",
        "acceptingOrders": True,
        "active": True,
        "closed": False,
    }
    payload.update(overrides)
    return payload


def make_unsorted_clob_payload(asset_id: str = "tok-yes") -> dict:
    """CLOB books are *not* sorted. Best bid is max, best ask is min."""
    return {
        "asset_id": asset_id,
        "bids": [
            {"price": "0.001", "size": "10"},
            {"price": "0.002", "size": "10"},
            {"price": "0.003", "size": "10"},
        ],
        "asks": [
            {"price": "0.999", "size": "10"},
            {"price": "0.998", "size": "10"},
            {"price": "0.004", "size": "10"},
        ],
        "tick_size": "0.001",
        "min_order_size": "5",
        "last_trade_price": "0.50",
        "market": "0xcondition",
    }


class FakeResponse:
    def raise_for_status(self):
        return None


class FakeSession:
    """requests-like session for Notifier tests. Never touches the network."""

    def __init__(self, fail: bool = False):
        self.calls: List[dict] = []
        self.fail = fail

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self.fail:
            raise RuntimeError("boom")
        return FakeResponse()


class FakeGamma:
    def __init__(self, markets: Iterable[Market] = ()):
        self.markets = list(markets)
        self.calls: List[dict] = []

    def hot_markets(self, limit: int = 40):
        self.calls.append({"limit": limit})
        return list(self.markets)


class FakeClob:
    def __init__(self):
        self.attached: List[list] = []

    def attach_books(self, markets):
        self.attached.append(list(markets))
        return list(markets)


class FakeTape:
    def __init__(self, prints: Optional[Sequence[Print]] = None, boom: bool = False):
        self.prints = list(prints or [])
        self.calls: List[dict] = []
        self.boom = boom

    def trades(self, **kwargs):
        self.calls.append(kwargs)
        if self.boom:
            raise RuntimeError("tape offline")
        return list(self.prints)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def unsorted_clob_payload():
    return make_unsorted_clob_payload()


@pytest.fixture
def gamma_payload():
    return make_gamma_payload()


@pytest.fixture
def completeness_market():
    """Yes ask 0.40 (100) + No ask 0.55 (80) → completeness size 80, edge 0.05."""
    return make_binary_market()


@pytest.fixture
def completeness_opportunity(completeness_market):
    return make_opportunity(completeness_market)


@pytest.fixture
def whale_print():
    return make_print()


@pytest.fixture
def empty_portfolio():
    return Portfolio(cash=1_000.0)


@pytest.fixture
def fake_session():
    return FakeSession()
