from __future__ import annotations

from typing import Sequence

from ..models import Opportunity
from .base import Decision, Strategy


class Completeness(Strategy):
    """Only the mechanical pair trades: buy both asks < $1, or sell both bids > $1."""

    name = "completeness"

    def decide(self, opportunities: Sequence[Opportunity], portfolio) -> Decision:
        limit = int(self.params.get("limit", 3))
        return self._take(opportunities, ("completeness", "merge"), limit=limit)
