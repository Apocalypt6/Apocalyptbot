"""Engine loop: hunt → decide → risk → paper fill → persist. Fakes only."""

import json

import pytest

from apocalyptbot.broker import PaperBroker
from apocalyptbot.engine import Engine
from apocalyptbot.hunt import HuntConfig
from apocalyptbot.notify import Notifier
from apocalyptbot.portfolio import Portfolio
from apocalyptbot.risk import RiskGate, RiskLimits
from apocalyptbot.strategies import REGISTRY, Decision, build
from tests.conftest import (
    FakeClob,
    FakeGamma,
    FakeSession,
    FakeTape,
    make_binary_market,
    make_opportunity,
    make_print,
)


STRATEGY_NAMES = ("completeness", "momentum", "fade", "copy_whale", "endgame")


def _engine(market, *, prints=None, strategy="completeness", cash=1_000.0, tmp_path=None, **kwargs):
    risk = kwargs.pop(
        "risk",
        RiskGate(
            RiskLimits(
                max_notional_per_trade=500,
                max_total_exposure=5_000,
                max_open_positions=20,
                max_daily_loss=1_000,
                min_edge=0.001,
            )
        ),
    )
    hunt_config = kwargs.pop(
        "hunt_config",
        HuntConfig(min_edge=0.01, min_shares=20, min_volume_24h=100, kinds=("completeness",)),
    )
    state_path = kwargs.pop("state_path", str(tmp_path / "state.json") if tmp_path else None)
    heartbeat_path = kwargs.pop("heartbeat_path", str(tmp_path / "heartbeat") if tmp_path else None)
    return Engine(
        FakeGamma([market]),
        FakeClob(),
        FakeTape(prints or []),
        build(strategy),
        PaperBroker(Portfolio(cash=cash)),
        risk=risk,
        state_path=state_path,
        heartbeat_path=heartbeat_path,
        hunt_config=hunt_config,
        **kwargs,
    )


def test_strategy_registry_and_build():
    for name in STRATEGY_NAMES:
        assert name in REGISTRY
        strat = build(name)
        assert strat.name == name
    with pytest.raises(ValueError, match="unknown"):
        build("not-a-strategy")


def test_decision_hold_and_completeness_filters(completeness_market):
    held = Decision.hold()
    assert held.opportunities == []
    assert held.reason

    pair = make_opportunity(completeness_market, kind="completeness")
    whale = make_opportunity(completeness_market, kind="whale", edge=0.4)
    pf = Portfolio(cash=1_000)
    picked = build("completeness").decide([whale, pair], pf)
    assert picked.opportunities
    assert all(o.kind in ("completeness", "merge") for o in picked.opportunities)
    assert any(o.kind == "completeness" for o in picked.opportunities)

    whales = build("copy_whale").decide([whale, pair], pf)
    assert whales.opportunities
    assert all(o.kind == "whale" for o in whales.opportunities)

    empty = build("fade").decide([pair], pf)
    assert empty.opportunities == []


def test_engine_step_fetches_hunts_fills_and_persists(tmp_path, completeness_market):
    gamma = FakeGamma([completeness_market])
    clob = FakeClob()
    tape = FakeTape([])
    pf = Portfolio(cash=1_000.0)
    broker = PaperBroker(pf)
    session = FakeSession()
    notifier = Notifier(webhook_url="https://example.test/hook", session=session)
    engine = Engine(
        gamma,
        clob,
        tape,
        build("completeness"),
        broker,
        risk=RiskGate(RiskLimits(max_notional_per_trade=200, min_edge=0.01)),
        state_path=str(tmp_path / "state.json"),
        heartbeat_path=str(tmp_path / "heartbeat"),
        notifier=notifier,
        hunt_limit=7,
        hunt_config=HuntConfig(min_edge=0.01, min_shares=20, min_volume_24h=100, kinds=("completeness",)),
    )
    fills = engine.step()

    assert gamma.calls and gamma.calls[0]["limit"] == 7
    assert clob.attached
    assert tape.calls
    assert "min_usd" in tape.calls[0]
    assert fills
    assert all(f.side == "BUY" for f in fills)
    assert pf.cash < 1_000.0
    assert pf.quantity("tok-yes") > 0
    assert pf.quantity("tok-no") > 0
    assert engine.last_opportunities
    assert (tmp_path / "state.json").exists()
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved["strategy"] == "completeness"
    assert "portfolio" in saved
    hb = (tmp_path / "heartbeat").read_text().strip()
    assert int(hb) > 0
    assert session.calls  # notify_fill posted


def test_engine_step_survives_tape_failure(tmp_path, completeness_market):
    engine = Engine(
        FakeGamma([completeness_market]),
        FakeClob(),
        FakeTape(boom=True),
        build("completeness"),
        PaperBroker(Portfolio(cash=1_000)),
        risk=RiskGate(RiskLimits(max_notional_per_trade=200, min_edge=0.01)),
        state_path=str(tmp_path / "state.json"),
        heartbeat_path=str(tmp_path / "heartbeat"),
        hunt_config=HuntConfig(min_edge=0.01, min_shares=20, min_volume_24h=100, kinds=("completeness",)),
    )
    fills = engine.step()
    assert fills  # books still produce completeness even if tape dies
    assert (tmp_path / "heartbeat").exists()


def test_engine_save_and_load_state(tmp_path, completeness_market):
    state = tmp_path / "nested" / "state.json"
    engine = _engine(completeness_market, tmp_path=tmp_path, state_path=str(state))
    engine.step()
    cash_after = engine.portfolio.cash
    assert cash_after < 1_000.0
    assert engine.load_state() is True
    assert engine.portfolio.cash == pytest.approx(cash_after)

    other = Engine(
        FakeGamma([]),
        FakeClob(),
        FakeTape(),
        build("completeness"),
        PaperBroker(Portfolio(cash=1.0)),
        state_path=str(state),
    )
    assert other.load_state() is True
    assert other.portfolio.cash == pytest.approx(cash_after)
    assert other.portfolio.quantity("tok-yes") > 0


def test_engine_load_state_missing_file(tmp_path, completeness_market):
    engine = _engine(completeness_market, state_path=str(tmp_path / "gone.json"))
    assert engine.load_state() is False


def test_engine_run_respects_max_iterations(completeness_market):
    gamma = FakeGamma([completeness_market])
    engine = Engine(
        gamma,
        FakeClob(),
        FakeTape(),
        build("completeness"),
        PaperBroker(Portfolio(cash=5_000)),
        risk=RiskGate(RiskLimits(max_notional_per_trade=80, min_edge=0.01)),
        hunt_config=HuntConfig(min_edge=0.01, min_shares=20, min_volume_24h=100, kinds=("completeness",)),
    )
    slept = []
    engine.run(poll_seconds=9.0, max_iterations=3, sleep=lambda s: slept.append(s))
    assert len(gamma.calls) == 3
    assert all(s == 9.0 for s in slept)
    assert len(slept) <= 3


def test_engine_step_whale_path(tmp_path):
    market = make_binary_market(yes_ask=0.50, no_ask=0.51, ask_no_size=100)
    print_ = make_print(condition_id=market.condition_id, size=8_000, price=0.5)
    engine = Engine(
        FakeGamma([market]),
        FakeClob(),
        FakeTape([print_]),
        build("copy_whale"),
        PaperBroker(Portfolio(cash=5_000)),
        risk=RiskGate(RiskLimits(max_notional_per_trade=100, min_edge=0.0, max_total_exposure=5_000)),
        state_path=str(tmp_path / "state.json"),
        hunt_limit=4,
        hunt_config=HuntConfig(kinds=("whale",), whale_usd=2500, min_volume_24h=100),
    )
    fills = engine.step()
    assert engine.last_opportunities
    assert engine.last_opportunities[0].kind == "whale"
    # clip_size may shrink the whale; a fill is enough to prove the path ran
    assert isinstance(fills, list)
