"""Paper broker: simulated order execution with fees and slippage.

This is deliberately conservative — it charges a taker fee and applies
slippage against you on every fill — so paper results don't look rosier
than reality. Swapping in a live broker later means implementing the same
``buy``/``sell`` surface against a real exchange API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .portfolio import Portfolio


@dataclass
class Fill:
    """Record of an executed simulated order."""

    symbol: str
    side: str  # "BUY" or "SELL"
    price: float  # effective price after slippage
    quantity: float
    fee: float
    timestamp: int
    cash_after: float
    realized_pnl: float = 0.0  # only meaningful on SELL

    def __str__(self) -> str:
        return (
            f"{self.side} {self.quantity:.8f} {self.symbol} @ {self.price:.2f} "
            f"(fee {self.fee:.4f}) -> cash {self.cash_after:.2f}"
        )


class PaperBroker:
    """Executes market orders against a :class:`Portfolio` in simulation."""

    def __init__(self, portfolio: Portfolio, fee_rate: float = 0.005, slippage: float = 0.0005):
        if not 0 <= fee_rate < 1:
            raise ValueError("fee_rate must be in [0, 1)")
        if not 0 <= slippage < 1:
            raise ValueError("slippage must be in [0, 1)")
        self.portfolio = portfolio
        self.fee_rate = fee_rate
        self.slippage = slippage
        self.min_notional = 1.0  # ignore dust orders

    def buy(self, symbol: str, price: float, cash_to_spend: float, timestamp: int) -> Optional[Fill]:
        """Spend up to ``cash_to_spend`` quote on ``symbol`` at ~``price``."""
        cash_to_spend = min(cash_to_spend, self.portfolio.cash)
        if cash_to_spend < self.min_notional or price <= 0:
            return None

        eff_price = price * (1 + self.slippage)
        fee = cash_to_spend * self.fee_rate
        quantity = (cash_to_spend - fee) / eff_price
        if quantity <= 0:
            return None

        self.portfolio.cash -= cash_to_spend
        pos = self.portfolio.position(symbol)
        pos.quantity += quantity
        pos.cost_basis += cash_to_spend  # include fee in cost basis

        return Fill(symbol, "BUY", eff_price, quantity, fee, timestamp, self.portfolio.cash)

    def sell(self, symbol: str, price: float, quantity: float, timestamp: int) -> Optional[Fill]:
        """Sell ``quantity`` of ``symbol`` at ~``price``."""
        pos = self.portfolio.position(symbol)
        quantity = min(quantity, pos.quantity)
        if quantity <= 0 or price <= 0:
            return None

        eff_price = price * (1 - self.slippage)
        gross = quantity * eff_price
        if gross < self.min_notional:
            return None
        fee = gross * self.fee_rate
        proceeds = gross - fee

        # Realized PnL vs. the average cost of the quantity sold.
        avg = pos.avg_price
        cost_of_sold = avg * quantity
        realized = proceeds - cost_of_sold

        self.portfolio.cash += proceeds
        pos.quantity -= quantity
        pos.cost_basis -= cost_of_sold
        if pos.quantity <= 1e-12:
            pos.quantity = 0.0
            pos.cost_basis = 0.0

        return Fill(symbol, "SELL", eff_price, quantity, fee, timestamp, self.portfolio.cash, realized)
