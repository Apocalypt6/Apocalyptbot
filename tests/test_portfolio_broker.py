"""Portfolio accounting and paper fills against constructed opportunities."""

import pytest

from apocalyptbot.broker import Fill, PaperBroker
from apocalyptbot.fees import fee_rate_for, taker_fee
from apocalyptbot.portfolio import Portfolio, Position
from tests.conftest import make_binary_market, make_opportunity


def test_position_fields():
    pos = Position(
        token_id="tok-yes",
        shares=10.0,
        cost=4.0,
        outcome="Yes",
        market_slug="will-x-happen",
        condition_id="0xcondition",
    )
    assert pos.token_id == "tok-yes"
    assert pos.shares == 10.0
    assert pos.cost == 4.0
    assert pos.outcome == "Yes"
    assert pos.market_slug == "will-x-happen"
    assert pos.condition_id == "0xcondition"
    assert pos.avg_price == pytest.approx(0.4)


def test_portfolio_equity_marks_to_mids():
    pf = Portfolio(cash=100.0)
    pos = pf.position("tok-yes")
    pos.shares = 10.0
    pos.cost = 4.0
    assert pf.equity({"tok-yes": 0.60}) == pytest.approx(100.0 + 10.0 * 0.60)
    # missing mark falls back to cost
    assert pf.equity({}) == pytest.approx(100.0 + 4.0)
    assert pf.quantity("tok-yes") == pytest.approx(10.0)
    assert pf.quantity("missing") == 0.0


def test_portfolio_to_dict_from_dict_roundtrip():
    pf = Portfolio(cash=250.0)
    pos = pf.position("tok-yes")
    pos.shares = 8.0
    pos.cost = 3.2
    pos.outcome = "Yes"
    pos.market_slug = "will-x-happen"
    pos.condition_id = "0xcondition"
    restored = Portfolio.from_dict(pf.to_dict())
    assert restored.cash == pytest.approx(250.0)
    assert restored.quantity("tok-yes") == pytest.approx(8.0)
    assert restored.equity({"tok-yes": 0.5}) == pytest.approx(pf.equity({"tok-yes": 0.5}))
    assert restored.positions["tok-yes"].outcome == "Yes"
    assert restored.positions["tok-yes"].market_slug == "will-x-happen"
    assert restored.positions["tok-yes"].condition_id == "0xcondition"


def test_fill_symbol_alias():
    named = Fill(
        token_id="tok-yes",
        side="BUY",
        price=0.4,
        shares=10,
        fee=0.0,
        ts=1,
        cash_after=100.0,
        market="will-x-happen",
        outcome="Yes",
    )
    assert named.symbol == "will-x-happen"
    bare = Fill(
        token_id="tok-yes",
        side="BUY",
        price=0.4,
        shares=10,
        fee=0.0,
        ts=1,
        cash_after=100.0,
        market="",
    )
    assert bare.symbol == "tok-yes"


def test_paper_broker_completeness_buys_both_legs():
    market = make_binary_market()
    opp = make_opportunity(market, size=80, yes_px=0.40, no_px=0.55)
    pf = Portfolio(cash=1_000.0)
    fills = PaperBroker(pf, slippage=0.0).execute(opp)
    assert len(fills) == 2
    assert all(f.side == "BUY" for f in fills)
    assert {f.token_id for f in fills} == {"tok-yes", "tok-no"}
    # fees_enabled is False on the fixture market → fee 0; cash -= price*shares
    expected = 0.40 * 80 + 0.55 * 80
    assert pf.cash == pytest.approx(1_000.0 - expected)
    assert pf.cash < 1_000.0
    assert pf.quantity("tok-yes") == pytest.approx(80)
    assert pf.quantity("tok-no") == pytest.approx(80)
    yes_pos = pf.positions["tok-yes"]
    assert yes_pos.outcome == "Yes"
    assert yes_pos.market_slug == market.slug
    assert yes_pos.condition_id == market.condition_id
    assert all(f.cash_after > 0 for f in fills)
    assert fills[-1].cash_after == pytest.approx(pf.cash)


def test_paper_broker_charges_taker_fee_when_market_has_fees():
    market = make_binary_market(fees_enabled=True, fee_type="sports_fees")
    opp = make_opportunity(market, size=80, yes_px=0.40, no_px=0.55)
    pf = Portfolio(cash=1_000.0)
    fills = PaperBroker(pf).execute(opp)
    rate = fee_rate_for(market)
    fee_yes = taker_fee(80, 0.40, rate)
    fee_no = taker_fee(80, 0.55, rate)
    assert {f.token_id: f.fee for f in fills}["tok-yes"] == pytest.approx(fee_yes)
    assert {f.token_id: f.fee for f in fills}["tok-no"] == pytest.approx(fee_no)
    assert pf.cash == pytest.approx(1_000.0 - (0.40 * 80 + 0.55 * 80 + fee_yes + fee_no))


def test_paper_broker_buy_insufficient_cash_raises():
    market = make_binary_market()
    opp = make_opportunity(market, size=80, yes_px=0.40, no_px=0.55)
    broker = PaperBroker(Portfolio(cash=1.0))
    with pytest.raises(RuntimeError, match="need"):
        broker.execute(opp)


def test_paper_broker_sell_requires_inventory_then_realizes():
    market = make_binary_market()
    buy = make_opportunity(market, size=80, yes_px=0.40, no_px=0.55, side="BUY")
    sell = make_opportunity(
        market, kind="merge", size=10, yes_px=0.60, no_px=0.50, side="SELL", edge=0.10
    )
    pf = Portfolio(cash=1_000.0)
    broker = PaperBroker(pf)
    with pytest.raises(RuntimeError, match="selling"):
        broker.execute(sell)
    broker.execute(buy)
    fills = broker.execute(sell)
    assert all(f.side == "SELL" for f in fills)
    assert pf.quantity("tok-yes") == pytest.approx(70)
    assert pf.quantity("tok-no") == pytest.approx(70)
    assert pf.cash > 1_000.0 - (0.40 * 80 + 0.55 * 80)  # sale proceeds returned
    assert any(f.realized_pnl != 0 for f in fills)


def test_paper_broker_slippage_worsens_buy_price():
    market = make_binary_market()
    opp = make_opportunity(market, size=10, yes_px=0.40, no_px=0.55)
    pf = Portfolio(cash=1_000.0)
    fills = PaperBroker(pf, slippage=0.01).execute(opp)
    by_token = {f.token_id: f for f in fills}
    assert by_token["tok-yes"].price == pytest.approx(min(0.40 * 1.01, 1.0))
    assert by_token["tok-no"].price == pytest.approx(min(0.55 * 1.01, 1.0))
