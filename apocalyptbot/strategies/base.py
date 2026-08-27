"""Strategy interface — pick among already-ranked opportunities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

from ..models import Opportunity


@dataclass
class Decision:
    opportunities: List[Opportunity] = field(default_factory=list)
    reason: str = "hold"

    @classmethod
    def hold(cls, reason: str = "nothing worth doing") -> "Decision":
        return cls(opportunities=[], reason=reason)

    @property
    def empty(self) -> bool:
        return not self.opportunities


class Strategy:
    name = "base"

    def __init__(self, **params):
        self.params = params

    def decide(self, opportunities: Sequence[Opportunity], portfolio) -> Decision:
        raise NotImplementedError

    def _take(
        self,
        opportunities: Sequence[Opportunity],
        kinds: Sequence[str],
        limit: int = 3,
        reason: str = "",
    ) -> Decision:
        picked = [opp for opp in opportunities if opp.kind in kinds][:limit]
        if not picked:
            return Decision.hold(reason or f"{self.name}: no {', '.join(kinds)} prints")
        return Decision(opportunities=picked, reason=reason or self.name)
