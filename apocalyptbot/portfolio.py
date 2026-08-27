"""Cash + outcome-token inventory."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Position:
    token_id: str
    shares: float = 0.0
    cost: float = 0.0
    outcome: str = ""
    market_slug: str = ""
    condition_id: str = ""

    @property
    def avg_price(self) -> float:
        if self.shares <= 0:
            return 0.0
        return self.cost / self.shares

    def to_dict(self) -> dict:
        return {
            "token_id": self.token_id,
            "shares": self.shares,
            "cost": self.cost,
            "outcome": self.outcome,
            "market_slug": self.market_slug,
            "condition_id": self.condition_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Position":
        return cls(
            token_id=data.get("token_id", ""),
            shares=float(data.get("shares") or 0),
            cost=float(data.get("cost") or 0),
            outcome=data.get("outcome") or "",
            market_slug=data.get("market_slug") or "",
            condition_id=data.get("condition_id") or "",
        )


@dataclass
class Portfolio:
    cash: float
    quote_currency: str = "pUSD"
    positions: Dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0

    def position(self, token_id: str) -> Position:
        if token_id not in self.positions:
            self.positions[token_id] = Position(token_id=token_id)
        return self.positions[token_id]

    def quantity(self, token_id: str) -> float:
        pos = self.positions.get(token_id)
        return pos.shares if pos else 0.0

    def exposure(self, prices: Optional[Dict[str, float]] = None) -> float:
        total = 0.0
        for token_id, pos in self.positions.items():
            if pos.shares <= 0:
                continue
            px = (prices or {}).get(token_id)
            total += pos.shares * px if px is not None else pos.cost
        return total

    def equity(self, prices: Optional[Dict[str, float]] = None) -> float:
        return self.cash + self.exposure(prices)

    def open_count(self) -> int:
        return sum(1 for pos in self.positions.values() if pos.shares > 1e-12)

    def to_dict(self) -> dict:
        return {
            "cash": self.cash,
            "quote_currency": self.quote_currency,
            "realized_pnl": self.realized_pnl,
            "positions": {k: v.to_dict() for k, v in self.positions.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Portfolio":
        raw_pos = data.get("positions") or {}
        return cls(
            cash=float(data.get("cash") or 0),
            quote_currency=data.get("quote_currency") or "pUSD",
            realized_pnl=float(data.get("realized_pnl") or 0),
            positions={k: Position.from_dict(v) for k, v in raw_pos.items()},
        )
