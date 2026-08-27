import json

from apocalyptbot.broker import PaperBroker
from apocalyptbot.engine import Engine
from apocalyptbot.hunt import HuntConfig, hunt
from apocalyptbot.models import Book, Level, Market, Opportunity, Outcome, Print
from apocalyptbot.notify import Notifier
from apocalyptbot.portfolio import Portfolio
from apocalyptbot.risk import RiskGate, RiskLimits
from apocalyptbot.strategies import build


def _binary(question="Will X happen?", vol=10_000, yes_ask=0.40, no_ask=0.55, yes_bid=0.39, no_bid=0.54, size=100):
    yes = Outcome(
        "Yes",
        "tok-yes",
        price=0.4,
        book=Book(
            "tok-yes",
            bids=[Level(yes_bid, size)],
            asks=[Level(yes_ask, size)],
        ),
    )
    no = Outcome(
        "No",
        "tok-no",
        price=0.6,
        book=Book(
            "tok-no",
            bids=[Level(no_bid, size)],
            asks=[Level(no_ask, size)],
        ),
    )
    return Market(
        id="1",
        condition_id="0xabc",
        question=question,
        slug="will-x-happen",
        outcomes=[yes, no],
        volume_24h=vol,
        accepting_orders=True,
        closed=False,
        min_order_size=5,
    )


def test_hunt_finds_completeness():
    market = _binary()
    opps = hunt([market], config=HuntConfig(min_edge=0.01, min_shares=20, min_volume_24h=100, kinds=("completeness",)))
    kinds = {o.kind for o in opps}
    assert "completeness" in kinds
    assert opps[0].edge > 0.04


def test_hunt_whale_print():
    market = _binary(yes_ask=0.50, no_ask=0.51)
    p = Print(
        wallet="0xdead",
        side="BUY",
        token_id="tok-yes",
        condition_id="0xabc",
        size=4000,
        price=0.5,
        usd=2000,
        title=market.question,
        slug=market.slug,
        outcome="Yes",
        timestamp=1,
        name="whale",
        tx="0x1",
    )
    # usd is computed in from_api; construct with matching usd
    p = Print.from_api(
        {
            "proxyWallet": "0xdead",
            "side": "BUY",
            "asset": "tok-yes",
            "conditionId": "0xabc",
            "size": 8000,
            "price": 0.5,
            "title": market.question,
            "slug": market.slug,
            "outcome": "Yes",
            "timestamp": 1,
            "name": "whale",
            "transactionHash": "0x1",
        }
    )
    assert p.usd == 4000
    opps = hunt(
        [market],
        prints=[p],
        config=HuntConfig(min_volume_24h=100, whale_usd=2500, kinds=("whale",)),
    )
    assert opps and opps[0].kind == "whale"


def test_portfolio_equity_roundtrip():
    pf = Portfolio(cash=1000)
    pos = pf.position("tok-yes")
    pos.shares = 10
    pos.cost = 4
    assert pf.equity({"tok-yes": 0.5}) == 1000 + 5
    restored = Portfolio.from_dict(pf.to_dict())
    assert restored.cash == 1000
    assert restored.quantity("tok-yes") == 10


def test_paper_broker_completeness():
    pf = Portfolio(cash=1000)
    broker = PaperBroker(pf)
    market = _binary()
    opps = hunt([market], config=HuntConfig(min_edge=0.01, min_shares=10, min_volume_24h=1, kinds=("completeness",)))
    fills = broker.execute(opps[0])
    assert len(fills) == 2
    assert all(f.side == "BUY" for f in fills)
    assert pf.cash < 1000
    assert pf.quantity("tok-yes") > 0
    assert pf.quantity("tok-no") > 0


def test_risk_clips_and_blocks():
    pf = Portfolio(cash=30)
    market = _binary()
    opp = hunt([market], config=HuntConfig(min_edge=0.01, min_shares=10, min_volume_24h=1, kinds=("completeness",)))[0]
    gate = RiskGate(RiskLimits(max_notional_per_trade=20, max_total_exposure=500, min_edge=0.01))
    clipped = gate.clip_size(opp, pf)
    assert clipped.notional <= 20 + 1e-6 or clipped.size == 0
    ok, _why = gate.allow(opp, pf, day_pnl=-200)
    assert ok is False


def test_engine_step_persists(tmp_path):
    market = _binary()

    class G:
        def hot_markets(self, limit=20):
            return [market]

    class C:
        def attach_books(self, markets):
            return list(markets)

    class T:
        def trades(self, **kwargs):
            return []

    pf = Portfolio(cash=1000)
    broker = PaperBroker(pf)
    state = tmp_path / "state.json"
    hb = tmp_path / "heartbeat"
    engine = Engine(
        G(),
        C(),
        T(),
        build("completeness"),
        broker,
        risk=RiskGate(RiskLimits(max_notional_per_trade=80, min_edge=0.01)),
        state_path=str(state),
        heartbeat_path=str(hb),
        hunt_limit=5,
        hunt_config=HuntConfig(min_edge=0.01, min_shares=10, min_volume_24h=1, kinds=("completeness",)),
    )
    fills = engine.step()
    assert fills
    assert state.exists()
    saved = json.loads(state.read_text())
    assert saved["strategy"] == "completeness"
    assert int(hb.read_text().strip()) > 0


def test_engine_run_iterations():
    market = _binary(yes_ask=0.50, no_ask=0.51)

    class G:
        def hot_markets(self, limit=20):
            return [market]

    class C:
        def attach_books(self, markets):
            return list(markets)

    class T:
        def trades(self, **kwargs):
            return []

    engine = Engine(G(), C(), T(), build("completeness"), PaperBroker(Portfolio(1000)))
    sleeps = []
    engine.run(poll_seconds=0.0, max_iterations=3, sleep=lambda s: sleeps.append(s))
    assert len(sleeps) <= 3


class FakeResponse:
    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json})
        if self.fail:
            raise RuntimeError("boom")
        return FakeResponse()


def test_notifier_webhook_and_fill():
    n = Notifier()
    assert n.enabled is False
    sess = FakeSession()
    n = Notifier(webhook_url="https://example.test/hook", session=sess)
    assert n.send("hi") is True
    assert sess.calls[0]["json"]["content"] == "hi"
    assert sess.calls[0]["json"]["text"] == "hi"
    from apocalyptbot.broker import Fill

    n.notify_fill(Fill("t", "SELL", 0.4, 10, 0.1, 1, cash_after=9, realized_pnl=1.2, market="mkt", outcome="Yes"))
    assert "SELL" in sess.calls[-1]["json"]["content"]


def test_notifier_swallows_errors():
    n = Notifier(webhook_url="https://example.test/hook", session=FakeSession(fail=True))
    assert n.send("x") is False
