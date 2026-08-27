"""Paper fills, plus a live CLOB stub that refuses to be casual."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import List, Optional

from .fees import fee_rate_for, taker_fee
from .models import Opportunity
from .portfolio import Portfolio


@dataclass
class Fill:
    token_id: str
    side: str
    price: float
    shares: float
    fee: float
    ts: float
    cash_after: float
    realized_pnl: float = 0.0
    market: str = ""
    outcome: str = ""

    @property
    def symbol(self) -> str:
        return self.market or self.token_id


class PaperBroker:
    """Immediate taker fills at the opportunity's quoted prices.

    No partials, no latency, no disappearing size. Useful as a filter for
    bad ideas — not as a promise the CLOB will be there when you click.
    """

    def __init__(self, portfolio: Portfolio, slippage: float = 0.0):
        self.portfolio = portfolio
        self.slippage = slippage

    def execute(self, opportunity: Opportunity) -> List[Fill]:
        fills: List[Fill] = []
        rate = fee_rate_for(opportunity.market)
        slug = opportunity.market.slug if opportunity.market else ""
        now = time.time()

        for side, token_id, price, shares, name in opportunity.legs:
            if shares <= 0:
                continue
            side = side.upper()
            px = price * (1.0 + self.slippage) if side == "BUY" else price * (1.0 - self.slippage)
            px = min(max(px, 0.0), 1.0)
            fee = taker_fee(shares, px, rate)
            realized = 0.0
            pos = self.portfolio.position(token_id)
            pos.outcome = pos.outcome or name
            pos.market_slug = pos.market_slug or slug
            if opportunity.market:
                pos.condition_id = pos.condition_id or opportunity.market.condition_id

            if side == "BUY":
                cost = px * shares + fee
                if cost > self.portfolio.cash + 1e-9:
                    raise RuntimeError(
                        f"paper broker: need ${cost:.2f}, have ${self.portfolio.cash:.2f}"
                    )
                self.portfolio.cash -= cost
                pos.shares += shares
                pos.cost += px * shares
            elif side == "SELL":
                if pos.shares + 1e-9 < shares:
                    raise RuntimeError(
                        f"paper broker: selling {shares} {name} but hold {pos.shares}"
                    )
                proceeds = px * shares - fee
                avg = pos.avg_price
                realized = (px - avg) * shares - fee
                self.portfolio.cash += proceeds
                pos.cost -= avg * shares
                pos.shares -= shares
                self.portfolio.realized_pnl += realized
                if pos.shares <= 1e-12:
                    pos.shares = 0.0
                    pos.cost = 0.0
            else:
                raise ValueError(f"unknown side {side}")

            fills.append(
                Fill(
                    token_id=token_id,
                    side=side,
                    price=px,
                    shares=shares,
                    fee=fee,
                    ts=now,
                    cash_after=self.portfolio.cash,
                    realized_pnl=realized,
                    market=slug or opportunity.market.question[:48],
                    outcome=name,
                )
            )
        return fills


class LiveBroker:
    """Opt-in CLOB V2 poster. Import and credentials are checked at call time."""

    def __init__(
        self,
        portfolio: Optional[Portfolio] = None,
        private_key: Optional[str] = None,
        funder: Optional[str] = None,
        signature_type: int = 0,
        confirmed: bool = False,
    ):
        self.portfolio = portfolio
        self.private_key = private_key or os.environ.get("POLYMARKET_PRIVATE_KEY")
        self.funder = funder or os.environ.get("POLYMARKET_FUNDER")
        self.signature_type = int(
            os.environ.get("POLYMARKET_SIGNATURE_TYPE", signature_type) or 0
        )
        self.confirmed = confirmed

    def execute(self, opportunity: Opportunity) -> List[Fill]:
        if not self.confirmed:
            raise RuntimeError("live trading refused: pass --i-understand-this-risks-real-money")
        if not self.private_key:
            raise RuntimeError("live trading refused: set POLYMARKET_PRIVATE_KEY")
        try:
            from py_clob_client_v2 import (  # type: ignore
                ClobClient,
                OrderArgs,
                OrderType,
                PartialCreateOrderOptions,
                Side,
            )
        except ImportError as exc:
            raise RuntimeError(
                "live trading refused: pip install 'apocalyptbot[live]' "
                "(py-clob-client-v2). The archived py-clob-client will not work on CLOB V2."
            ) from exc

        host = os.environ.get("POLYMARKET_CLOB_HOST", "https://clob.polymarket.com")
        temp = ClobClient(host, key=self.private_key, chain_id=137)
        creds = temp.create_or_derive_api_key()
        client = ClobClient(
            host,
            key=self.private_key,
            chain_id=137,
            creds=creds,
            signature_type=self.signature_type,
            funder=self.funder or "",
        )

        fills: List[Fill] = []
        tick = str(opportunity.market.tick_size if opportunity.market else "0.01")
        now = time.time()
        for side, token_id, price, shares, name in opportunity.legs:
            side_enum = Side.BUY if side.upper() == "BUY" else Side.SELL
            resp = client.create_and_post_order(
                order_args=OrderArgs(
                    token_id=token_id,
                    price=float(price),
                    side=side_enum,
                    size=float(shares),
                ),
                options=PartialCreateOrderOptions(
                    tick_size=tick,
                    neg_risk=bool(opportunity.market.neg_risk) if opportunity.market else False,
                ),
                order_type=OrderType.GTC,
            )
            fills.append(
                Fill(
                    token_id=token_id,
                    side=side.upper(),
                    price=float(price),
                    shares=float(shares),
                    fee=0.0,
                    ts=now,
                    cash_after=self.portfolio.cash if self.portfolio else 0.0,
                    market=opportunity.market.slug if opportunity.market else "",
                    outcome=name,
                )
            )
            # Keep a breadcrumb so operators can match the CLOB ack.
            fills[-1].realized_pnl = 0.0
            _ = resp
        return fills
