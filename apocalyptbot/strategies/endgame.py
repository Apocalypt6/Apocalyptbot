from __future__ import annotations

from typing import Sequence

from ..models import Opportunity
from .base import Decision, Strategy


class Endgame(Strategy):
    """Markets near resolution at extreme prices. Black swans live here."""

    name = "endgame"

    def decide(self, opportunities: Sequence[Opportunity], portfolio) -> Decision:
        limit = int(self.params.get("limit", 1))
        return self._take(opportunities, ("endgame",), limit=limit, reason="endgame")
