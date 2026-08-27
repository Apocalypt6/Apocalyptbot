"""Environment-backed settings for unattended runs."""

from __future__ import annotations

import os
from dataclasses import dataclass


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


@dataclass
class Config:
    mode: str = "hunt"
    strategy: str = "completeness"
    cash: float = 1000.0
    poll_seconds: float = 30.0
    hunt_limit: int = 40
    min_edge: float = 0.008
    min_shares: float = 20.0
    max_notional: float = 50.0
    max_exposure: float = 500.0
    max_daily_loss: float = 75.0
    state_path: str = "state/portfolio.state.json"
    heartbeat_path: str = "state/heartbeat"

    @classmethod
    def from_env(cls, env=None) -> "Config":
        env = env if env is not None else os.environ
        return cls(
            mode=env.get("MODE", "hunt"),
            strategy=env.get("STRATEGY", "completeness"),
            cash=_f("CASH", 1000.0) if env is os.environ else float(env.get("CASH") or 1000),
            poll_seconds=float(env.get("POLL_SECONDS") or 30),
            hunt_limit=int(env.get("HUNT_LIMIT") or 40),
            min_edge=float(env.get("MIN_EDGE") or 0.008),
            min_shares=float(env.get("MIN_SHARES") or 20),
            max_notional=float(env.get("MAX_NOTIONAL") or 50),
            max_exposure=float(env.get("MAX_EXPOSURE") or 500),
            max_daily_loss=float(env.get("MAX_DAILY_LOSS") or 75),
            state_path=env.get("STATE_PATH", "state/portfolio.state.json"),
            heartbeat_path=env.get("HEARTBEAT_PATH", "state/heartbeat"),
        )
