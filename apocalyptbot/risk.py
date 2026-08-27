"""Hard caps. The hunter finds trades; this decides which ones may fire."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .models import Opportunity
from .portfolio import Portfolio


@dataclass
class RiskLimits:
    max_notional_per_trade: float = 100.0
    max_total_exposure: float = 1000.0
    max_open_positions: int = 20
    max_daily_loss: float = 100.0
    min_edge: float = 0.008


class RiskGate:
    def __init__(self, limits: RiskLimits = None):
        self.limits = limits or RiskLimits()

    def allow(self, opp: Opportunity, portfolio: Portfolio, day_pnl: float = 0.0) -> Tuple[bool, str]:
        if opp.kind == "merge":
            for side, token_id, _px, shares, name in opp.legs:
                if side == "SELL" and portfolio.quantity(token_id) + 1e-9 < shares:
                    return False, f"merge needs inventory of {name}"
        if opp.kind not in ("merge",) and opp.edge + 1e-12 < self.limits.min_edge:
            if opp.kind in ("completeness",):
                return False, f"edge {opp.edge:.4f} below min {self.limits.min_edge:.4f}"
        if day_pnl <= -abs(self.limits.max_daily_loss):
            return False, f"daily loss cap hit ({day_pnl:.2f})"
        if portfolio.open_count() >= self.limits.max_open_positions and opp.kind != "merge":
            return False, "too many open positions"
        if portfolio.exposure() >= self.limits.max_total_exposure and opp.kind != "merge":
            return False, "total exposure cap"
        if opp.notional > 0 and portfolio.cash <= 0 and any(s == "BUY" for s, *_ in opp.legs):
            return False, "no cash"
        return True, "ok"

    def clip_size(self, opp: Opportunity, portfolio: Portfolio) -> Opportunity:
        shares = opp.size
        if shares <= 0:
            return opp

        if opp.notional > 0 and opp.size > 0:
            max_by_notional = self.limits.max_notional_per_trade * opp.size / opp.notional
            shares = min(shares, max_by_notional)

            buy_notional = sum(px * qty for side, _t, px, qty, _n in opp.legs if side == "BUY")
            if buy_notional > 0:
                max_by_cash = portfolio.cash * 0.98 * opp.size / buy_notional
                shares = min(shares, max_by_cash)

            headroom = self.limits.max_total_exposure - portfolio.exposure()
            if headroom > 0:
                shares = min(shares, headroom * opp.size / opp.notional)
            else:
                if any(s == "BUY" for s, *_ in opp.legs):
                    shares = 0.0

        min_size = opp.market.min_order_size if opp.market else 5.0
        if shares + 1e-12 < min_size:
            return opp.with_size(0.0)
        return opp.with_size(shares)
