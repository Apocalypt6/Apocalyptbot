"""Taker-fee curve and category rate mapping."""

from apocalyptbot.fees import DEFAULT_FEE_RATE, FEE_RATES, fee_rate_for, taker_fee
from apocalyptbot.models import Market


def _market(*, fees_enabled=True, fee_type="crypto_fees"):
    return Market(
        id="1",
        condition_id="0x",
        question="q",
        slug="s",
        fees_enabled=fees_enabled,
        fee_type=fee_type,
    )


def test_fee_rates_published_categories():
    assert FEE_RATES["crypto_fees"] == 0.07
    assert FEE_RATES["crypto_fees_v2"] == 0.07
    assert FEE_RATES["sports_fees"] == 0.05
    assert FEE_RATES["sports_fees_v2"] == 0.05
    assert FEE_RATES["politics_fees"] == 0.04
    assert FEE_RATES["finance_fees"] == 0.04
    assert FEE_RATES["geopolitics_fees"] == 0.0
    assert DEFAULT_FEE_RATE == 0.05


def test_fee_rate_override_wins_even_when_market_is_none():
    assert fee_rate_for(None, override=0.12) == 0.12
    m = _market(fees_enabled=True, fee_type="crypto_fees")
    assert fee_rate_for(m, override=0.01) == 0.01
    assert fee_rate_for(m, override=0.0) == 0.0


def test_fee_rate_none_or_disabled_is_zero():
    assert fee_rate_for(None) == 0.0
    assert fee_rate_for(_market(fees_enabled=False, fee_type="crypto_fees")) == 0.0


def test_fee_rate_maps_known_types():
    assert fee_rate_for(_market(fee_type="crypto_fees")) == 0.07
    assert fee_rate_for(_market(fee_type="crypto_fees_v2")) == 0.07
    assert fee_rate_for(_market(fee_type="sports_fees")) == 0.05
    assert fee_rate_for(_market(fee_type="politics_fees")) == 0.04
    assert fee_rate_for(_market(fee_type="geopolitics_fees")) == 0.0


def test_fee_rate_unknown_or_blank_defaults_to_five_percent():
    assert fee_rate_for(_market(fee_type="no_such_fees")) == 0.05
    assert fee_rate_for(_market(fee_type="")) == 0.05
    assert fee_rate_for(_market(fee_type=None)) == 0.05


def test_fee_rate_strips_fee_type_whitespace():
    assert fee_rate_for(_market(fee_type="  crypto_fees  ")) == 0.07


def test_taker_fee_official_midpoint_examples():
    # fee = shares * fee_rate * price * (1 - price), rounded to 5 decimals
    assert taker_fee(100, 0.50, 0.07) == 1.75  # crypto
    assert taker_fee(100, 0.50, 0.05) == 1.25  # sports
    assert taker_fee(100, 0.50, 0.04) == 1.00  # politics


def test_taker_fee_zero_when_shares_or_rate_nonpositive():
    assert taker_fee(0, 0.50, 0.05) == 0.0
    assert taker_fee(-10, 0.50, 0.05) == 0.0
    assert taker_fee(100, 0.50, 0.0) == 0.0
    assert taker_fee(100, 0.50, -0.01) == 0.0


def test_taker_fee_rounds_to_five_decimals():
    raw = 17 * 0.05 * 0.33 * (1.0 - 0.33)
    assert taker_fee(17, 0.33, 0.05) == round(raw + 1e-12, 5)


def test_taker_fee_clamps_price_to_unit_interval():
    # price 1.0 or 0.0 → p*(1-p) = 0
    assert taker_fee(100, 1.0, 0.05) == 0.0
    assert taker_fee(100, 0.0, 0.05) == 0.0
    # out-of-range prices are clamped, not used raw
    assert taker_fee(100, 1.5, 0.05) == 0.0
    assert taker_fee(100, -0.2, 0.05) == 0.0
