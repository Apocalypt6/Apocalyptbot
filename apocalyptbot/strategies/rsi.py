"""RSI mean-reversion: buy oversold dips, sell overbought spikes.

Buys when RSI drops below an oversold threshold (price may be due to bounce)
and sells when it rises above an overbought threshold. Works best in
range-bound markets; can get run over by strong trends — again, backtest first.
"""

from __future__ import annotations

from typing import List

from ..data import Candle, closes
from ..indicators import rsi
from ..portfolio import Portfolio
from .base import Decision, Strategy


class RsiStrategy(Strategy):
    name = "rsi"

    def __init__(self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0, allocation: float = 1.0):
        if not 0 < oversold < overbought < 100:
            raise ValueError("require 0 < oversold < overbought < 100")
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.allocation = max(0.0, min(1.0, allocation))

    def decide(self, symbol: str, candles: List[Candle], portfolio: Portfolio) -> Decision:
        prices = closes(candles)
        line = rsi(prices, self.period)
        value = line[-1] if line else None
        if value is None:
            return Decision.hold("warming up")

        holding = portfolio.quantity(symbol) > 0
        if value <= self.oversold and not holding:
            return Decision.buy(self.allocation, f"RSI {value:.1f} <= {self.oversold} (oversold)")
        if value >= self.overbought and holding:
            return Decision.sell(1.0, f"RSI {value:.1f} >= {self.overbought} (overbought)")
        return Decision.hold(f"RSI {value:.1f} in neutral zone")

    def warmup(self) -> int:
        return self.period + 1
