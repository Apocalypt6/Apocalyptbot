"""Risk gate: allow / deny and clip_size against notional and cash."""

import pytest

from apocalyptbot.portfolio import Portfolio
from apocalyptbot.risk import RiskGate, RiskLimits
from tests.conftest import make_binary_market, make_opportunity


def test_risk_limits_defaults():
    limits = RiskLimits()
    assert limits.max_notional_per_trade == 100
    assert limits.max_total_exposure == 1000
    assert limits.max_open_positions == 20
    assert limits.max_daily_loss == 100
    assert limits.min_edge == 0.008


def _gate(**kwargs) -> RiskGate:
    return RiskGate(RiskLimits(**kwargs))


def test_allow_good_completeness(completeness_opportunity, empty_portfolio):
    ok, reason = _gate(min_edge=0.008).allow(completeness_opportunity, empty_portfolio, 0.0)
    assert ok is True
    assert reason


def test_allow_rejects_completeness_below_min_edge(completeness_market):
    opp = make_opportunity(completeness_market, edge=0.001, size=80)
    ok, reason = _gate(min_edge=0.008).allow(opp, Portfolio(cash=1_000), 0.0)
    assert ok is False
    assert reason


def test_allow_rejects_daily_loss_cap(completeness_opportunity):
    ok, reason = _gate(max_daily_loss=100).allow(
        completeness_opportunity, Portfolio(cash=1_000), day_pnl=-100.0
    )
    assert ok is False
    assert "daily" in reason.lower() or "loss" in reason.lower()


def test_allow_rejects_no_cash_on_buy(completeness_opportunity):
    ok, reason = _gate().allow(completeness_opportunity, Portfolio(cash=0.0), 0.0)
    assert ok is False
    assert "cash" in reason.lower()


def test_allow_rejects_too_many_open_positions(completeness_opportunity):
    pf = Portfolio(cash=1_000)
    for i in range(20):
        pf.position(f"tok-{i}").shares = 1.0
        pf.position(f"tok-{i}").cost = 0.5
    ok, reason = _gate(max_open_positions=20).allow(completeness_opportunity, pf, 0.0)
    assert ok is False
    assert "position" in reason.lower()


def test_allow_rejects_exposure_cap(completeness_opportunity):
    pf = Portfolio(cash=1_000)
    pf.position("already").shares = 100
    pf.position("already").cost = 1_000
    ok, reason = _gate(max_total_exposure=1_000).allow(completeness_opportunity, pf, 0.0)
    assert ok is False
    assert "exposure" in reason.lower()


def test_allow_merge_requires_inventory(completeness_market):
    merge = make_opportunity(
        completeness_market, kind="merge", side="SELL", size=10, yes_px=0.60, no_px=0.50, edge=0.10
    )
    empty = Portfolio(cash=1_000)
    ok, reason = _gate().allow(merge, empty, 0.0)
    assert ok is False
    assert "inventory" in reason.lower()

    funded = Portfolio(cash=1_000)
    funded.position("tok-yes").shares = 20
    funded.position("tok-no").shares = 20
    ok, reason = _gate().allow(merge, funded, 0.0)
    assert ok is True


def test_clip_size_fits_max_notional_per_trade(completeness_market):
    # size 80, notional 76 → cap $10 ⇒ ~10.53 shares, notional $10
    opp = make_opportunity(completeness_market, size=80, yes_px=0.40, no_px=0.55)
    pf = Portfolio(cash=10_000)
    clipped = _gate(max_notional_per_trade=10, max_total_exposure=10_000).clip_size(opp, pf)
    assert clipped.size < opp.size
    assert clipped.notional == pytest.approx(10.0, abs=1e-6)
    assert clipped.legs[0][3] < 80


def test_clip_size_fits_available_cash(completeness_market):
    opp = make_opportunity(completeness_market, size=80, yes_px=0.40, no_px=0.55)
    # buy_notional = 76; cash $20 → shares = 20*0.98*80/76 ≈ 20.63
    clipped = _gate(max_notional_per_trade=10_000, max_total_exposure=10_000).clip_size(
        opp, Portfolio(cash=20.0)
    )
    assert clipped.size < opp.size
    assert clipped.notional <= 20.0 + 1e-6


def test_clip_size_leaves_fitting_trade_alone(completeness_opportunity):
    pf = Portfolio(cash=10_000)
    clipped = _gate(max_notional_per_trade=500, max_total_exposure=5_000).clip_size(
        completeness_opportunity, pf
    )
    assert clipped.size == pytest.approx(completeness_opportunity.size)
    assert clipped.notional == pytest.approx(completeness_opportunity.notional)
