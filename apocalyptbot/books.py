"""Order-book math. Completeness / merge edge is the whole point."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .fees import taker_fee
from .models import Book, Level, Leg

FillSlice = Tuple[float, float]  # avg_price, filled_shares


def _sorted_asks(book: Book) -> List[Level]:
    return sorted(book.asks, key=lambda lvl: lvl.price)


def _sorted_bids(book: Book) -> List[Level]:
    return sorted(book.bids, key=lambda lvl: lvl.price, reverse=True)


def walk_asks(book: Book, shares: float) -> FillSlice:
    """Take `shares` from the ask side. Returns (avg_price, filled)."""
    return _walk(_sorted_asks(book), shares)


def walk_bids(book: Book, shares: float) -> FillSlice:
    """Hit `shares` on the bid side. Returns (avg_price, filled)."""
    return _walk(_sorted_bids(book), shares)


def _walk(levels: Sequence[Level], shares: float) -> FillSlice:
    if shares <= 0:
        return 0.0, 0.0
    filled = 0.0
    cost = 0.0
    remaining = shares
    for lvl in levels:
        take = min(remaining, lvl.size)
        if take <= 0:
            continue
        cost += take * lvl.price
        filled += take
        remaining -= take
        if remaining <= 1e-12:
            break
    if filled <= 0:
        return 0.0, 0.0
    return cost / filled, filled


def _paired_walk(
    left: Sequence[Level],
    right: Sequence[Level],
    fee_rate: float,
    min_edge: float,
    max_shares: Optional[float],
    payout: float,
    buy: bool,
) -> Optional[dict]:
    """Walk two books in lockstep (1:1 shares) while edge stays above min_edge.

    `payout` is $1.00 for a complete binary set at resolution.
    For buys, edge = payout - avg_left - avg_right - fees.
    For sells, edge = avg_left + avg_right - payout - fees.
    """
    if not left or not right:
        return None

    i = j = 0
    left_rem = left[0].size
    right_rem = right[0].size
    filled = 0.0
    left_cost = 0.0
    right_cost = 0.0
    fees = 0.0

    best: Optional[dict] = None

    while i < len(left) and j < len(right):
        cap = min(left_rem, right_rem)
        if max_shares is not None:
            cap = min(cap, max_shares - filled)
        if cap <= 1e-12:
            break

        lp = left[i].price
        rp = right[j].price
        step_fee = taker_fee(cap, lp, fee_rate) + taker_fee(cap, rp, fee_rate)
        if buy:
            step_edge_cash = cap * payout - cap * lp - cap * rp - step_fee
        else:
            step_edge_cash = cap * lp + cap * rp - cap * payout - step_fee

        # Adding this slice must not pull average edge below min_edge.
        new_filled = filled + cap
        new_left = left_cost + cap * lp
        new_right = right_cost + cap * rp
        new_fees = fees + step_fee
        if buy:
            edge = (new_filled * payout - new_left - new_right - new_fees) / new_filled
        else:
            edge = (new_left + new_right - new_filled * payout - new_fees) / new_filled

        if edge + 1e-12 < min_edge or step_edge_cash < 0:
            break

        filled = new_filled
        left_cost = new_left
        right_cost = new_right
        fees = new_fees
        left_rem -= cap
        right_rem -= cap
        best = {
            "edge": edge,
            "size": filled,
            "left_avg": left_cost / filled,
            "right_avg": right_cost / filled,
            "fees": fees,
            "notional": (left_cost + right_cost + fees) if buy else (left_cost + right_cost - fees),
        }

        if left_rem <= 1e-12:
            i += 1
            if i < len(left):
                left_rem = left[i].size
        if right_rem <= 1e-12:
            j += 1
            if j < len(right):
                right_rem = right[j].size
        if max_shares is not None and filled >= max_shares - 1e-12:
            break

    return best


def completeness_buy(
    yes_book: Book,
    no_book: Book,
    fee_rate: float,
    min_edge: float = 0.0,
    max_shares: Optional[float] = None,
    yes_name: str = "Yes",
    no_name: str = "No",
) -> Optional[dict]:
    """Buy both outcomes when ask(YES) + ask(NO) + fees < $1."""
    raw = _paired_walk(
        _sorted_asks(yes_book),
        _sorted_asks(no_book),
        fee_rate,
        min_edge,
        max_shares,
        payout=1.0,
        buy=True,
    )
    if raw is None:
        return None
    legs: Tuple[Leg, ...] = (
        ("BUY", yes_book.token_id, raw["left_avg"], raw["size"], yes_name),
        ("BUY", no_book.token_id, raw["right_avg"], raw["size"], no_name),
    )
    raw["legs"] = legs
    raw["yes_avg"] = raw["left_avg"]
    raw["no_avg"] = raw["right_avg"]
    return raw


def merge_sell(
    yes_book: Book,
    no_book: Book,
    fee_rate: float,
    min_edge: float = 0.0,
    max_shares: Optional[float] = None,
    yes_name: str = "Yes",
    no_name: str = "No",
) -> Optional[dict]:
    """Sell both outcomes when bid(YES) + bid(NO) - fees > $1 (needs inventory)."""
    raw = _paired_walk(
        _sorted_bids(yes_book),
        _sorted_bids(no_book),
        fee_rate,
        min_edge,
        max_shares,
        payout=1.0,
        buy=False,
    )
    if raw is None:
        return None
    legs: Tuple[Leg, ...] = (
        ("SELL", yes_book.token_id, raw["left_avg"], raw["size"], yes_name),
        ("SELL", no_book.token_id, raw["right_avg"], raw["size"], no_name),
    )
    raw["legs"] = legs
    raw["yes_avg"] = raw["left_avg"]
    raw["no_avg"] = raw["right_avg"]
    return raw
