"""Portfolio and position accounting for the paper broker."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping


@dataclass
class Position:
    """A holding of one asset. ``cost_basis`` is total quote spent on it."""

    quantity: float = 0.0
    cost_basis: float = 0.0

    @property
    def avg_price(self) -> float:
        return self.cost_basis / self.quantity if self.quantity > 0 else 0.0


@dataclass
class Portfolio:
    """Cash plus per-symbol positions, valued in a single quote currency."""

    cash: float
    quote_currency: str = "USD"
    positions: Dict[str, Position] = field(default_factory=dict)

    def position(self, symbol: str) -> Position:
        return self.positions.setdefault(symbol, Position())

    def quantity(self, symbol: str) -> float:
        return self.positions.get(symbol, Position()).quantity

    def market_value(self, prices: Mapping[str, float]) -> float:
        """Value of all positions at the given prices (excludes cash)."""
        total = 0.0
        for symbol, pos in self.positions.items():
            if symbol in prices:
                total += pos.quantity * prices[symbol]
        return total

    def equity(self, prices: Mapping[str, float]) -> float:
        """Total account value: cash + marked-to-market positions."""
        return self.cash + self.market_value(prices)

    def to_dict(self) -> dict:
        return {
            "cash": self.cash,
            "quote_currency": self.quote_currency,
            "positions": {
                s: {"quantity": p.quantity, "cost_basis": p.cost_basis}
                for s, p in self.positions.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Portfolio":
        pf = cls(cash=float(data["cash"]), quote_currency=data.get("quote_currency", "USD"))
        for symbol, p in data.get("positions", {}).items():
            pf.positions[symbol] = Position(
                quantity=float(p["quantity"]), cost_basis=float(p["cost_basis"])
            )
        return pf
