"""Moving-average crossover: a classic trend-following strategy.

Go long when the fast SMA crosses above the slow SMA (uptrend forming),
exit to cash when it crosses back below (uptrend fading). Simple and
intuitive, but whipsaws in choppy markets — which is exactly why you
backtest it before trusting it.
"""

from __future__ import annotations

from typing import List

from ..data import Candle, closes
from ..indicators import crossed_down, crossed_up, sma
from ..portfolio import Portfolio
from .base import Decision, Strategy


class SmaCrossoverStrategy(Strategy):
    name = "sma_crossover"

    def __init__(self, fast: int = 10, slow: int = 30, allocation: float = 1.0):
        if fast >= slow:
            raise ValueError("fast period must be shorter than slow period")
        self.fast = fast
        self.slow = slow
        self.allocation = max(0.0, min(1.0, allocation))

    def decide(self, symbol: str, candles: List[Candle], portfolio: Portfolio) -> Decision:
        prices = closes(candles)
        if len(prices) <= self.slow:
            return Decision.hold("warming up")

        fast_line = sma(prices, self.fast)
        slow_line = sma(prices, self.slow)
        f_now, f_prev = fast_line[-1], fast_line[-2]
        s_now, s_prev = slow_line[-1], slow_line[-2]
        if None in (f_now, f_prev, s_now, s_prev):
            return Decision.hold("warming up")

        holding = portfolio.quantity(symbol) > 0
        if crossed_up(f_prev, f_now, s_prev, s_now) and not holding:
            return Decision.buy(self.allocation, "fast SMA crossed above slow")
        if crossed_down(f_prev, f_now, s_prev, s_now) and holding:
            return Decision.sell(1.0, "fast SMA crossed below slow")
        return Decision.hold("no crossover")

    def warmup(self) -> int:
        return self.slow + 1
