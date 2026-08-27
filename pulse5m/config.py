"""Load Settings from environment. Never print secrets."""

from __future__ import annotations

import os
from pathlib import Path

from strategy import Settings, default_settings


def _f(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return float(raw)


def _i(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _b(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    base = default_settings()
    assets = os.environ.get("PULSE_ASSETS", ",".join(base.assets))
    mode = os.environ.get("PULSE_MODE", base.mode).strip().lower()
    if mode not in {"paper", "live"}:
        mode = "paper"
    strategy = os.environ.get("PULSE_STRATEGY", base.strategy).strip().lower()
    if strategy not in {"lock", "hybrid"}:
        strategy = "lock"
    return Settings(
        assets=[a.strip().lower() for a in assets.split(",") if a.strip()],
        size_usd=_f("PULSE_SIZE_USD", base.size_usd),
        max_ask=_f("PULSE_MAX_ASK", base.max_ask),
        min_ask=_f("PULSE_MIN_ASK", base.min_ask),
        min_edge=_f("PULSE_MIN_EDGE", base.min_edge),
        min_ev=_f("PULSE_MIN_EV", base.min_ev),
        entry_from_sec=_f("PULSE_ENTRY_FROM", base.entry_from_sec),
        entry_to_sec=_f("PULSE_ENTRY_TO", base.entry_to_sec),
        max_spread=_f("PULSE_MAX_SPREAD", base.max_spread),
        daily_loss_halt=_f("PULSE_DAILY_LOSS_HALT", base.daily_loss_halt),
        max_consecutive_losses=_i("PULSE_MAX_LOSSES", base.max_consecutive_losses),
        bankroll=_f("PULSE_BANKROLL", base.bankroll),
        mode=mode,
        strategy=strategy,
        require_max_tier=_b("PULSE_REQUIRE_MAX_TIER", base.require_max_tier),
        kelly_fraction=_f("PULSE_KELLY", base.kelly_fraction),
        enable_arb=_b("PULSE_ENABLE_ARB", base.enable_arb),
        persist_ticks=_i("PULSE_PERSIST_TICKS", base.persist_ticks),
        max_edge=_f("PULSE_MAX_EDGE", base.max_edge),
    )


def data_dir() -> Path:
    raw = os.environ.get("PULSE_DATA")
    if raw:
        p = Path(raw)
    else:
        p = Path(__file__).resolve().parent / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p
