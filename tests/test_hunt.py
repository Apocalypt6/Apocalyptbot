"""Hunter: completeness / merge / tape / endgame from constructed books."""

from datetime import datetime, timedelta, timezone

import pytest

from apocalyptbot.hunt import HuntConfig, hunt
from apocalyptbot.models import Book, Level, Market, Outcome
from tests.conftest import make_binary_market, make_print


def test_hunt_config_defaults():
    cfg = HuntConfig()
    assert cfg.min_edge == 0.008
    assert cfg.min_shares == 20.0
    assert cfg.min_volume_24h == 500.0
    assert cfg.wide_spread == 0.04
    assert cfg.endgame_hours == 36.0
    assert cfg.endgame_prob == 0.92
    assert cfg.whale_usd == 2500.0
    assert "completeness" in cfg.kinds
    assert "whale" in cfg.kinds


def test_hunt_completeness_when_asks_sum_below_one_minus_min_edge():
    market = make_binary_market(yes_ask=0.40, no_ask=0.55, ask_yes_size=100, ask_no_size=80, volume_24h=10_000)
    opps = hunt(
        [market],
        config=HuntConfig(min_edge=0.01, min_shares=20, min_volume_24h=500, kinds=("completeness",)),
    )
    assert opps
    assert all(o.kind == "completeness" for o in opps)
    assert opps[0].edge == pytest.approx(0.05)
    assert opps[0].size == pytest.approx(80)
    assert opps[0].market.slug == market.slug
    assert len(opps[0].legs) == 2
    assert {leg[0] for leg in opps[0].legs} == {"BUY"}


def test_hunt_skips_low_volume_and_closed_and_not_accepting():
    cfg = HuntConfig(min_edge=0.01, min_shares=20, min_volume_24h=500, kinds=("completeness",))
    thin = make_binary_market(volume_24h=100)
    closed = make_binary_market(volume_24h=10_000, closed=True)
    halted = make_binary_market(volume_24h=10_000, accepting_orders=False)
    assert hunt([thin], config=cfg) == []
    assert hunt([closed], config=cfg) == []
    assert hunt([halted], config=cfg) == []


def test_hunt_no_completeness_when_asks_do_not_clear_min_edge():
    market = make_binary_market(yes_ask=0.50, no_ask=0.50, ask_no_size=100, volume_24h=10_000)
    opps = hunt([market], config=HuntConfig(min_edge=0.008, kinds=("completeness",)))
    assert opps == []


def test_hunt_merge_when_bids_sum_above_one():
    market = make_binary_market(
        yes_bid=0.60,
        no_bid=0.50,
        bid_yes_size=50,
        bid_no_size=40,
        yes_ask=0.99,
        no_ask=0.99,
        volume_24h=8_000,
    )
    opps = hunt(
        [market],
        config=HuntConfig(min_edge=0.01, min_shares=20, min_volume_24h=500, kinds=("merge",)),
    )
    assert opps
    assert opps[0].kind == "merge"
    assert opps[0].size == pytest.approx(40)
    assert opps[0].edge == pytest.approx(0.10)
    assert {leg[0] for leg in opps[0].legs} == {"SELL"}


def test_hunt_whale_when_print_meets_floor_and_kind_enabled(whale_print):
    market = make_binary_market(yes_ask=0.50, no_ask=0.51, ask_no_size=100)
    assert whale_print.usd >= 2500
    opps = hunt(
        [market],
        prints=[whale_print],
        config=HuntConfig(min_volume_24h=100, whale_usd=2500, kinds=("whale",)),
    )
    assert opps
    assert opps[0].kind == "whale"
    assert opps[0].notional == pytest.approx(whale_print.usd)
    assert opps[0].size == pytest.approx(whale_print.size)


def test_hunt_whale_skipped_when_kind_disabled_or_too_small():
    market = make_binary_market(yes_ask=0.50, no_ask=0.51, ask_no_size=100)
    small = make_print(size=100, price=0.5)  # $50
    assert small.usd < 2500
    assert (
        hunt(
            [market],
            prints=[small],
            config=HuntConfig(kinds=("whale",), whale_usd=2500, min_volume_24h=100),
        )
        == []
    )
    big = make_print(size=10_000, price=0.5)  # $5000
    opps = hunt(
        [market],
        prints=[big],
        config=HuntConfig(kinds=("completeness",), whale_usd=2500, min_volume_24h=100),
    )
    assert all(o.kind != "whale" for o in opps)


def test_hunt_whale_synthesizes_market_when_condition_unknown():
    orphan = make_print(condition_id="0xmissing", usd=5000, size=10_000, price=0.5)
    opps = hunt([], prints=[orphan], config=HuntConfig(kinds=("whale",), whale_usd=2500))
    assert opps and opps[0].kind == "whale"
    assert opps[0].market.condition_id == "0xmissing"


def test_hunt_wide_spread():
    book = Book(token_id="tok-yes", bids=[Level(0.40, 50)], asks=[Level(0.50, 50)])
    market = Market(
        id="w",
        condition_id="0xwide",
        question="wide?",
        slug="wide",
        outcomes=[Outcome("Yes", "tok-yes", price=0.45, book=book)],
        volume_24h=5_000,
        accepting_orders=True,
        closed=False,
    )
    opps = hunt(
        [market],
        config=HuntConfig(kinds=("wide_spread",), wide_spread=0.04, min_shares=20, min_volume_24h=100),
    )
    assert opps
    assert opps[0].kind == "wide_spread"
    assert opps[0].edge == pytest.approx(0.10)


def test_hunt_endgame_near_resolution():
    end = datetime.now(timezone.utc) + timedelta(hours=12)
    book = Book(token_id="tok-yes", bids=[Level(0.94, 100)], asks=[Level(0.96, 100)])
    market = Market(
        id="e",
        condition_id="0xend",
        question="already over?",
        slug="endgame",
        outcomes=[Outcome("Yes", "tok-yes", price=0.95, book=book)],
        volume_24h=5_000,
        accepting_orders=True,
        closed=False,
        end_date=end.isoformat(),
        min_order_size=5.0,
    )
    opps = hunt(
        [market],
        config=HuntConfig(kinds=("endgame",), endgame_hours=36, endgame_prob=0.92, min_volume_24h=100),
    )
    assert opps
    assert opps[0].kind == "endgame"


def test_hunt_ranks_by_score_descending():
    cheap = make_binary_market(
        yes_ask=0.30, no_ask=0.50, ask_no_size=200, volume_24h=50_000, condition_id="0x1", slug="a"
    )
    mild = make_binary_market(
        yes_ask=0.45, no_ask=0.52, ask_no_size=80, volume_24h=1_000, condition_id="0x2", slug="b"
    )
    opps = hunt(
        [mild, cheap],
        config=HuntConfig(min_edge=0.01, min_shares=20, min_volume_24h=100, kinds=("completeness",)),
    )
    assert len(opps) >= 2
    scores = [o.score for o in opps]
    assert scores == sorted(scores, reverse=True)


def test_hunt_default_config_is_used_when_omitted():
    # default min_volume_24h is 500; a $100 book is ignored
    assert hunt([make_binary_market(volume_24h=100)]) == []
