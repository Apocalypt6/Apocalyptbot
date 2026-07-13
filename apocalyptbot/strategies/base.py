"""Strategy interface.

A strategy is a pure decision function: given the price history so far and
the current portfolio, return what it wants to do next. It never touches the
broker directly — the engine/backtester translates a :class:`Decision` into
orders. Keeping strategies side-effect-free makes them trivial to backtest
and unit-test.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import List

from ..data import Candle
from ..portfolio import Portfolio


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class Decision:
    """What a strategy wants to do at the current candle.

    ``size`` is a fraction in [0, 1]:
      * BUY  -> fraction of available cash to spend
      * SELL -> fraction of the current position to sell
    It is ignored for HOLD.
    """

    signal: Signal
    size: float = 1.0
    reason: str = ""

    @classmethod
    def hold(cls, reason: str = "") -> "Decision":
        return cls(Signal.HOLD, 0.0, reason)

    @classmethod
    def buy(cls, size: float = 1.0, reason: str = "") -> "Decision":
        return cls(Signal.BUY, _clamp(size), reason)

    @classmethod
    def sell(cls, size: float = 1.0, reason: str = "") -> "Decision":
        return cls(Signal.SELL, _clamp(size), reason)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


class Strategy(ABC):
    """Base class for all strategies."""

    name: str = "strategy"

    @abstractmethod
    def decide(self, symbol: str, candles: List[Candle], portfolio: Portfolio) -> Decision:
        """Return a decision given all candles up to and including the current one."""

    def warmup(self) -> int:
        """Minimum number of candles needed before decisions are meaningful."""
        return 1

    def __str__(self) -> str:
        return self.name
