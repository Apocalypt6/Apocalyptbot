"""5m and 15m clock. Settlement lookback is 60s on BOTH (live Gamma 27 Aug 2026)."""

from __future__ import annotations

import time
from typing import Literal

Timeframe = Literal["5m", "15m"]

TF_SECONDS: dict[str, int] = {"5m": 300, "15m": 900}
TF_SLUG: dict[str, str] = {"5m": "5m", "15m": "15m"}
LOOKBACK_S = 60.0
ALL_FRAMES: tuple[str, ...] = ("5m", "15m")

TF_SCRIPTS: dict[str, tuple[str, ...]] = {
    "5m": ("arb", "lock", "snipe"),
    "15m": ("arb", "lock", "snipe", "hedge", "fair"),
}

TF_FAIR_FROM: dict[str, float] = {"5m": 180.0, "15m": 420.0}
TF_FAIR_TO: dict[str, float] = {"5m": 70.0, "15m": 70.0}

SCRIPT_PRIORITY: tuple[str, ...] = ("arb", "lock", "snipe", "hedge", "fair")


def window_of(tf: str, unix: float | None = None) -> int:
    dur = TF_SECONDS[tf]
    t = int(unix if unix is not None else time.time())
    return t // dur * dur


def seconds_left(tf: str, unix: float | None = None) -> float:
    t = float(unix if unix is not None else time.time())
    win = window_of(tf, t)
    return win + TF_SECONDS[tf] - t


def slug_of(asset: str, tf: str, window_start: int) -> str:
    return f"{asset}-updown-{TF_SLUG[tf]}-{window_start}"


def market_key(tf: str, asset: str, window_start: int) -> str:
    return f"{tf}:{asset}:{window_start}"


def strike_key(asset: str, tf: str, window_start: int) -> str:
    return f"{asset}:{tf}:{window_start}"


def close_of(tf: str, window_start: int) -> int:
    return window_start + TF_SECONDS[tf]


def shares_close(tf_a: str, win_a: int, tf_b: str, win_b: int) -> bool:
    """True when two windows expire on the same UTC second (last 5m of a 15m)."""
    return close_of(tf_a, win_a) == close_of(tf_b, win_b)
