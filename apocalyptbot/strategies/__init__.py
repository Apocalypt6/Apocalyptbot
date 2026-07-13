"""Built-in strategies and a small registry/factory."""

from __future__ import annotations

from typing import Dict, Type

from .base import Decision, Signal, Strategy
from .dca import DCAStrategy
from .rsi import RsiStrategy
from .sma_crossover import SmaCrossoverStrategy

REGISTRY: Dict[str, Type[Strategy]] = {
    DCAStrategy.name: DCAStrategy,
    SmaCrossoverStrategy.name: SmaCrossoverStrategy,
    RsiStrategy.name: RsiStrategy,
}


def build(name: str, **params) -> Strategy:
    """Instantiate a strategy by name with keyword parameters."""
    try:
        cls = REGISTRY[name]
    except KeyError:
        raise ValueError(f"unknown strategy {name!r}; available: {sorted(REGISTRY)}") from None
    return cls(**params)


__all__ = [
    "Decision",
    "Signal",
    "Strategy",
    "DCAStrategy",
    "RsiStrategy",
    "SmaCrossoverStrategy",
    "REGISTRY",
    "build",
]
