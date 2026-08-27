from __future__ import annotations

from typing import Dict, Type

from .base import Decision, Strategy
from .completeness import Completeness
from .copy_whale import CopyWhale
from .endgame import Endgame
from .fade import Fade
from .momentum import Momentum

REGISTRY: Dict[str, Type[Strategy]] = {
    "completeness": Completeness,
    "momentum": Momentum,
    "fade": Fade,
    "copy_whale": CopyWhale,
    "endgame": Endgame,
}


def build(name: str, **params) -> Strategy:
    key = (name or "").strip().lower()
    if key not in REGISTRY:
        known = ", ".join(sorted(REGISTRY))
        raise ValueError(f"unknown strategy {name!r}; choose one of: {known}")
    return REGISTRY[key](**params)


__all__ = ["Decision", "Strategy", "REGISTRY", "build"]
