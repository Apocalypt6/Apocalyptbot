import json

from apocalyptbot import strategies
from apocalyptbot.broker import PaperBroker
from apocalyptbot.data import synthetic
from apocalyptbot.engine import TradingEngine
from apocalyptbot.portfolio import Portfolio


def test_portfolio_equity_and_roundtrip():
    pf = Portfolio(cash=1000.0)
    pf.position("BTC-USD").quantity = 2.0
    pf.position("BTC-USD").cost_basis = 200.0
    assert pf.equity({"BTC-USD": 150.0}) == 1000.0 + 2.0 * 150.0

    restored = Portfolio.from_dict(pf.to_dict())
    assert restored.cash == pf.cash
    assert restored.quantity("BTC-USD") == 2.0


def test_engine_step_executes_and_persists(tmp_path):
    candles = synthetic(n=100, seed=1)
    pf = Portfolio(cash=1000.0)
    broker = PaperBroker(pf, fee_rate=0.005, slippage=0.0005)
    strat = strategies.build("dca", every=1, amount=100.0)  # buys every step
    state = tmp_path / "state.json"

    engine = TradingEngine(lambda: candles, strat, broker, symbol="BTC-USD", state_path=str(state))
    fill = engine.step()

    assert fill is not None
    assert pf.cash < 1000.0
    assert state.exists()
    saved = json.loads(state.read_text())
    assert saved["symbol"] == "BTC-USD"
    assert saved["strategy"] == "dca"


def test_engine_run_stops_after_iterations():
    candles = synthetic(n=100, seed=2)
    pf = Portfolio(cash=1000.0)
    broker = PaperBroker(pf)
    strat = strategies.build("sma_crossover", fast=5, slow=20)
    engine = TradingEngine(lambda: candles, strat, broker, symbol="BTC-USD")

    calls = []
    engine.run(poll_seconds=0.0, max_iterations=3, sleep=lambda s: calls.append(s))
    # Loop sleeps between iterations, so it sleeps at most iterations-1 times.
    assert len(calls) <= 3


def test_engine_state_restore(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({
        "symbol": "BTC-USD",
        "strategy": "dca",
        "portfolio": {"cash": 555.0, "quote_currency": "USD", "positions": {}},
    }))
    pf = Portfolio(cash=1000.0)
    broker = PaperBroker(pf)
    engine = TradingEngine(lambda: [], strategies.build("dca"), broker, symbol="BTC-USD", state_path=str(state))
    assert engine.load_state() is True
    assert engine.portfolio.cash == 555.0
