"""Dollar-cost averaging: buy a fixed amount on a fixed cadence.

The simplest, least stressful strategy — no market timing, just steady
accumulation. Historically a solid approach for long-term crypto exposure,
and a good baseline every fancier strategy should be measured against.
"""

from __future__ import annotations

from typing import List

from ..data import Candle
from ..portfolio import Portfolio
from .base import Decision, Strategy


class DCAStrategy(Strategy):
    name = "dca"

    def __init__(self, every: int = 24, amount: float = 100.0):
        """Buy ``amount`` (quote currency) once every ``every`` candles."""
        if every <= 0:
            raise ValueError("every must be positive")
        if amount <= 0:
            raise ValueError("amount must be positive")
        self.every = every
        self.amount = amount

    def decide(self, symbol: str, candles: List[Candle], portfolio: Portfolio) -> Decision:
        # Trigger on a fixed cadence based on how many candles we've seen.
        # Using len() keeps the strategy stateless and backtest-reproducible.
        if len(candles) % self.every != 0:
            return Decision.hold("not a buy interval")
        if portfolio.cash < min(self.amount, 1.0):
            return Decision.hold("out of cash")
        fraction = min(1.0, self.amount / portfolio.cash)
        return Decision.buy(fraction, f"scheduled DCA buy of ~{self.amount:.2f}")

    def warmup(self) -> int:
        return 1
