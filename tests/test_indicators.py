import math

import pytest

from apocalyptbot.indicators import crossed_down, crossed_up, ema, rsi, sma


def test_sma_basic():
    values = [1, 2, 3, 4, 5]
    out = sma(values, 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)
    assert out[3] == pytest.approx(3.0)
    assert out[4] == pytest.approx(4.0)


def test_sma_period_one_is_identity():
    values = [5.0, 7.0, 9.0]
    assert sma(values, 1) == pytest.approx(values)


def test_ema_matches_known_values():
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    out = ema(values, 3)
    # First value seeded with SMA of first 3 = 2.0
    assert out[2] == pytest.approx(2.0)
    # k = 0.5 for period 3: next = 4*0.5 + 2*0.5 = 3.0
    assert out[3] == pytest.approx(3.0)
    assert out[-1] is not None and out[-1] > out[3]


def test_rsi_all_gains_is_100():
    values = list(range(1, 30))  # strictly increasing
    out = rsi(values, 14)
    assert out[-1] == pytest.approx(100.0)


def test_rsi_all_losses_is_zero():
    values = list(range(30, 1, -1))  # strictly decreasing
    out = rsi(values, 14)
    assert out[-1] == pytest.approx(0.0)


def test_rsi_bounds():
    values = [math.sin(i / 3) * 10 + 100 for i in range(100)]
    out = rsi(values, 14)
    for v in out:
        if v is not None:
            assert 0.0 <= v <= 100.0


def test_crossovers():
    assert crossed_up(1, 3, 2, 2) is True
    assert crossed_up(3, 4, 2, 2) is False  # already above
    assert crossed_down(3, 1, 2, 2) is True
    assert crossed_down(1, 0.5, 2, 2) is False  # already below


def test_invalid_period():
    with pytest.raises(ValueError):
        sma([1, 2, 3], 0)
    with pytest.raises(ValueError):
        rsi([1, 2, 3], -1)
