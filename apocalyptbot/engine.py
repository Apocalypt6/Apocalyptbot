"""Hunt loop: discover → book → score → risk → paper/live fill → persist."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Callable, List, Optional

from .broker import Fill, PaperBroker
from .clob import Clob
from .gamma import Gamma
from .hunt import HuntConfig, hunt
from .models import Opportunity
from .notify import Notifier
from .portfolio import Portfolio
from .risk import RiskGate, RiskLimits
from .strategies.base import Strategy
from .tape import Tape

logger = logging.getLogger("apocalyptbot.engine")


class Engine:
    def __init__(
        self,
        gamma: Gamma,
        clob: Clob,
        tape: Tape,
        strategy: Strategy,
        broker: PaperBroker,
        risk: Optional[RiskGate] = None,
        state_path: Optional[str] = None,
        heartbeat_path: Optional[str] = None,
        notifier: Optional[Notifier] = None,
        hunt_limit: int = 20,
        hunt_config: Optional[HuntConfig] = None,
        day_start_equity: Optional[float] = None,
    ):
        self.gamma = gamma
        self.clob = clob
        self.tape = tape
        self.strategy = strategy
        self.broker = broker
        self.risk = risk or RiskGate(RiskLimits())
        self.state_path = state_path
        self.heartbeat_path = heartbeat_path
        self.notifier = notifier
        self.hunt_limit = hunt_limit
        self.hunt_config = hunt_config or HuntConfig()
        self.day_start_equity = day_start_equity
        self.last_opportunities: List[Opportunity] = []
        self.last_reason: str = ""

    @property
    def portfolio(self) -> Portfolio:
        return self.broker.portfolio

    def _prices(self, markets) -> dict:
        prices = {}
        for market in markets:
            for outcome in market.outcomes:
                if outcome.book and outcome.book.mid is not None:
                    prices[outcome.token_id] = outcome.book.mid
                elif outcome.price is not None:
                    prices[outcome.token_id] = outcome.price
        return prices

    def step(self) -> List[Fill]:
        markets = self.gamma.hot_markets(limit=self.hunt_limit)
        self.clob.attach_books(markets)
        prints = []
        try:
            prints = self.tape.trades(limit=80, min_usd=self.hunt_config.whale_usd, taker_only=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("tape failed: %s", exc)

        opps = hunt(markets, prints=prints, config=self.hunt_config)
        self.last_opportunities = opps
        decision = self.strategy.decide(opps, self.portfolio)
        self.last_reason = decision.reason

        prices = self._prices(markets)
        equity = self.portfolio.equity(prices)
        if self.day_start_equity is None:
            self.day_start_equity = equity
        day_pnl = equity - self.day_start_equity

        fills: List[Fill] = []
        for opp in decision.opportunities:
            clipped = self.risk.clip_size(opp, self.portfolio)
            if clipped.size <= 0:
                logger.info("risk clipped %s to zero", opp.kind)
                continue
            ok, why = self.risk.allow(clipped, self.portfolio, day_pnl)
            if not ok:
                logger.info("risk blocked %s: %s", opp.kind, why)
                continue
            try:
                new_fills = self.broker.execute(clipped)
            except Exception as exc:  # noqa: BLE001
                logger.error("execute failed: %s", exc)
                if self.notifier:
                    self.notifier.send(f"execute failed: {exc}")
                continue
            fills.extend(new_fills)
            for fill in new_fills:
                logger.info(
                    "FILL %s %s %s @ %.4f x %.2f",
                    fill.side,
                    fill.outcome,
                    fill.market,
                    fill.price,
                    fill.shares,
                )
                if self.notifier:
                    self.notifier.notify_fill(fill)

        self._heartbeat()
        self.save_state()
        return fills

    def run(self, poll_seconds: float = 30.0, max_iterations: Optional[int] = None, sleep: Callable = time.sleep):
        n = 0
        while True:
            self.step()
            n += 1
            if max_iterations is not None and n >= max_iterations:
                return
            sleep(poll_seconds)

    def _heartbeat(self) -> None:
        if not self.heartbeat_path:
            return
        parent = os.path.dirname(self.heartbeat_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(self.heartbeat_path, "w") as fh:
            fh.write(str(int(time.time())))

    def save_state(self) -> None:
        if not self.state_path:
            return
        parent = os.path.dirname(self.state_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        payload = {
            "strategy": self.strategy.name,
            "portfolio": self.portfolio.to_dict(),
            "day_start_equity": self.day_start_equity,
        }
        with open(self.state_path, "w") as fh:
            json.dump(payload, fh, indent=2)

    def load_state(self) -> bool:
        if not self.state_path or not os.path.exists(self.state_path):
            return False
        with open(self.state_path) as fh:
            payload = json.load(fh)
        self.broker.portfolio = Portfolio.from_dict(payload.get("portfolio") or {})
        self.day_start_equity = payload.get("day_start_equity")
        return True
