"""Live/paper trading engine.

Polls a data source on the candle cadence, asks the strategy for a decision,
routes it through the broker, persists portfolio state to disk, and logs what
happened. Today the broker is the paper (simulated) broker; wiring a real
exchange broker in later means giving it the same ``buy``/``sell`` methods —
the engine loop does not change.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Callable, List, Optional

from .broker import Fill, PaperBroker
from .data import Candle
from .notify import Notifier
from .portfolio import Portfolio
from .strategies.base import Signal, Strategy

logger = logging.getLogger("apocalyptbot.engine")


class TradingEngine:
    """Drives one strategy on one symbol against a data source and broker."""

    def __init__(
        self,
        data_fetch: Callable[[], List[Candle]],
        strategy: Strategy,
        broker: PaperBroker,
        symbol: str,
        state_path: Optional[str] = None,
        notifier: Optional[Notifier] = None,
        heartbeat_path: Optional[str] = None,
    ):
        """``data_fetch`` returns the latest candles (oldest-first) on each call."""
        self.data_fetch = data_fetch
        self.strategy = strategy
        self.broker = broker
        self.symbol = symbol
        self.state_path = state_path
        self.notifier = notifier
        self.heartbeat_path = heartbeat_path

    @property
    def portfolio(self) -> Portfolio:
        return self.broker.portfolio

    def step(self) -> Optional[Fill]:
        """Fetch fresh data, make one decision, execute it. Returns any fill."""
        candles = self.data_fetch()
        if len(candles) < self.strategy.warmup():
            logger.info("waiting for warmup: %d/%d candles", len(candles), self.strategy.warmup())
            return None

        price = candles[-1].close
        ts = candles[-1].timestamp
        decision = self.strategy.decide(self.symbol, candles, self.portfolio)
        logger.info("decision=%s size=%.3f price=%.2f (%s)", decision.signal.value, decision.size, price, decision.reason)

        fill: Optional[Fill] = None
        if decision.signal is Signal.BUY:
            fill = self.broker.buy(self.symbol, price, self.portfolio.cash * decision.size, ts)
        elif decision.signal is Signal.SELL:
            qty = self.portfolio.quantity(self.symbol) * decision.size
            fill = self.broker.sell(self.symbol, price, qty, ts)

        if fill:
            logger.info("FILL %s", fill)
            self.save_state()
            if self.notifier:
                self.notifier.notify_fill(fill)
        equity = self.portfolio.equity({self.symbol: price})
        logger.info("equity=%.2f cash=%.2f position=%.8f", equity, self.portfolio.cash, self.portfolio.quantity(self.symbol))
        self._write_heartbeat()
        return fill

    def run(self, poll_seconds: float, max_iterations: Optional[int] = None, sleep: Callable[[float], None] = time.sleep) -> None:
        """Poll-and-trade loop. ``max_iterations=None`` runs until interrupted."""
        logger.info("engine start: %s on %s, polling every %ss", self.strategy.name, self.symbol, poll_seconds)
        if self.notifier:
            self.notifier.send(f"🟢 Apocalyptbot started: {self.strategy.name} on {self.symbol}")
        count = 0
        try:
            while max_iterations is None or count < max_iterations:
                try:
                    self.step()
                except Exception as exc:  # noqa: BLE001 - keep the loop alive on transient errors
                    logger.exception("step failed; will retry next cycle")
                    if self.notifier:
                        self.notifier.notify_error("step", exc)
                count += 1
                if max_iterations is not None and count >= max_iterations:
                    break
                sleep(poll_seconds)
        except KeyboardInterrupt:
            logger.info("interrupted; saving state and exiting")
            self.save_state()

    # --- health & persistence ---------------------------------------------

    def _write_heartbeat(self) -> None:
        """Touch the heartbeat file with the current unix time (for healthchecks)."""
        if not self.heartbeat_path:
            return
        try:
            parent = os.path.dirname(os.path.abspath(self.heartbeat_path))
            os.makedirs(parent, exist_ok=True)
            with open(self.heartbeat_path, "w") as fh:
                fh.write(str(int(time.time())))
        except OSError:
            logger.warning("could not write heartbeat to %s", self.heartbeat_path, exc_info=True)

    def save_state(self) -> None:
        if not self.state_path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.state_path)), exist_ok=True)
        with open(self.state_path, "w") as fh:
            json.dump({"symbol": self.symbol, "strategy": self.strategy.name, "portfolio": self.portfolio.to_dict()}, fh, indent=2)

    def load_state(self) -> bool:
        if not self.state_path or not os.path.exists(self.state_path):
            return False
        with open(self.state_path) as fh:
            data = json.load(fh)
        self.broker.portfolio = Portfolio.from_dict(data["portfolio"])
        logger.info("restored state from %s", self.state_path)
        return True
