"""Configuration model.

Loaded from a JSON file and/or CLI flags. Note that API keys are read from
the environment only and are never part of a committed config file — see
the README's security section.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Config:
    symbol: str = "BTC-USD"
    interval: str = "1h"
    exchange: str = "coinbase"  # data source for live/paper mode

    starting_cash: float = 10_000.0
    fee_rate: float = 0.005
    slippage: float = 0.0005

    strategy: str = "sma_crossover"
    strategy_params: Dict[str, Any] = field(default_factory=dict)

    poll_seconds: float = 3600.0
    state_path: str = "state/portfolio.state.json"

    @classmethod
    def from_file(cls, path: str) -> "Config":
        with open(path) as fh:
            data = json.load(fh)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    # API keys, if ever needed for live trading, come from the environment.
    @staticmethod
    def api_key() -> Optional[str]:
        return os.environ.get("APOCALYPTBOT_API_KEY")

    @staticmethod
    def api_secret() -> Optional[str]:
        return os.environ.get("APOCALYPTBOT_API_SECRET")
