"""Polymarket taker fees.

Official curve (2026):

    fee = shares * fee_rate * price * (1 - price)

Makers are not charged. Geopolitics is fee-free. `takerBaseFee` on Gamma is
currently 1000 for every fee-enabled category, so we map `feeType` to the
published category rates instead of trusting that integer.
"""

from __future__ import annotations

from typing import Optional

from .models import Market

# Published category taker rates. Keys are Gamma `feeType` values.
FEE_RATES = {
    "crypto_fees": 0.07,
    "crypto_fees_v2": 0.07,
    "sports_fees": 0.05,
    "sports_fees_v2": 0.05,
    "sports_fees_v3": 0.05,
    "finance_fees": 0.04,
    "finance_prices_fees": 0.04,
    "politics_fees": 0.04,
    "economics_fees": 0.05,
    "culture_fees": 0.05,
    "weather_fees": 0.05,
    "tech_fees": 0.04,
    "mentions_fees": 0.04,
    "geopolitics_fees": 0.0,
}

DEFAULT_FEE_RATE = 0.05


def fee_rate_for(market: Optional[Market], override: Optional[float] = None) -> float:
    if override is not None:
        return float(override)
    if market is None or not market.fees_enabled:
        return 0.0
    key = (market.fee_type or "").strip()
    if key in FEE_RATES:
        return FEE_RATES[key]
    return DEFAULT_FEE_RATE


def taker_fee(shares: float, price: float, fee_rate: float) -> float:
    """USDC fee for a taker fill, rounded to 5 decimals (protocol precision)."""
    if shares <= 0 or fee_rate <= 0:
        return 0.0
    p = min(max(price, 0.0), 1.0)
    raw = shares * fee_rate * p * (1.0 - p)
    return round(raw + 1e-12, 5)
