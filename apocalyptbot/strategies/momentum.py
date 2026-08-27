from __future__ import annotations

from typing import Sequence

from ..models import Opportunity
from .base import Decision, Strategy


class Momentum(Strategy):
    """Ride large tape. This is gambling with extra steps."""

    name = "momentum"

    def decide(self, opportunities: Sequence[Opportunity], portfolio) -> Decision:
        limit = int(self.params.get("limit", 2))
        return self._take(opportunities, ("whale", "endgame"), limit=limit, reason="momentum follow")
