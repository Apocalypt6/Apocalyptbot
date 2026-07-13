import pytest

from apocalyptbot import strategies
from apocalyptbot.backtest import run_backtest
from apocalyptbot.data import Candle, synthetic
from apocalyptbot.portfolio import Portfolio
from apocalyptbot.strategies.base import Signal


def _flat_candles(prices):
    return [Candle(i, p, p, p, p, 1.0) for i, p in enumerate(prices)]


def test_synthetic_is_deterministic():
    a = synthetic(n=50, seed=42)
    b = synthetic(n=50, seed=42)
    assert [c.close for c in a] == [c.close for c in b]
    assert len(a) == 50


def test_registry_builds_all():
    for name in strategies.REGISTRY:
        assert strategies.build(name) is not None


def test_unknown_strategy_raises():
    with pytest.raises(ValueError):
        strategies.build("nope")


def test_dca_buys_on_schedule():
    strat = strategies.build("dca", every=5, amount=100.0)
    pf = Portfolio(cash=1000.0)
    # At a length that is a multiple of 5 -> buy
    candles = _flat_candles([100.0] * 5)
    d = strat.decide("BTC-USD", candles, pf)
    assert d.signal is Signal.BUY
    # Not a multiple -> hold
    candles = _flat_candles([100.0] * 4)
    assert strat.decide("BTC-USD", candles, pf).signal is Signal.HOLD


def test_sma_crossover_generates_trades_on_trend_reversal():
    # A flat stretch (so both SMAs settle equal) then a rise (genuine cross up
    # -> buy) then a fall (cross down -> sell). A purely monotonic series would
    # cross only during the SMA warmup blind spot and correctly trade zero times.
    flat = [50.0] * 30
    up = [50.0 + i for i in range(1, 41)]      # 51 .. 90
    down = [90.0 - i for i in range(1, 51)]    # 89 .. 40
    candles = _flat_candles(flat + up + down)
    strat = strategies.build("sma_crossover", fast=5, slow=20)
    result = run_backtest(candles, strat, symbol="X", starting_cash=1000.0, fee_rate=0.0, slippage=0.0)
    sides = [f.side for f in result.fills]
    assert "BUY" in sides and "SELL" in sides
    assert result.metrics["num_trades"] >= 2


def test_sma_crossover_requires_fast_lt_slow():
    with pytest.raises(ValueError):
        strategies.build("sma_crossover", fast=30, slow=10)


def test_rsi_strategy_runs():
    candles = synthetic(n=200, seed=3)
    strat = strategies.build("rsi", period=14, oversold=30, overbought=70)
    result = run_backtest(candles, strat, symbol="X", starting_cash=1000.0)
    assert "total_return" in result.metrics
    assert result.final_equity > 0


def test_backtest_reports_buy_and_hold():
    # Steadily rising market: buy & hold should be strongly positive.
    candles = _flat_candles([100.0 * (1.01 ** i) for i in range(100)])
    strat = strategies.build("dca", every=10, amount=100.0)
    result = run_backtest(candles, strat, symbol="X", starting_cash=1000.0, fee_rate=0.0, slippage=0.0)
    assert result.metrics["buy_hold_return"] > 0
    assert 0.0 <= result.metrics["max_drawdown"] <= 1.0
    assert result.metrics["bars"] > 0


def test_backtest_needs_two_candles():
    with pytest.raises(ValueError):
        run_backtest(_flat_candles([100.0]), strategies.build("dca"))


def test_no_lookahead_all_in_then_hold_matches_buy_hold():
    # An all-in-on-first-bar DCA (every=1 huge amount) should roughly track price.
    prices = [100.0, 110.0, 121.0]
    candles = _flat_candles(prices)
    strat = strategies.build("dca", every=1, amount=1_000_000.0)
    result = run_backtest(candles, strat, symbol="X", starting_cash=1000.0, fee_rate=0.0, slippage=0.0)
    # Fully invested at 100, price rises 21% -> equity ~1210
    assert result.final_equity == pytest.approx(1210.0, rel=1e-6)
