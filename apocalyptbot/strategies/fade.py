from __future__ import annotations

from typing import Sequence

from ..models import Opportunity
from .base import Decision, Strategy


class Fade(Strategy):
    """Lean on wide books. Edge is the spread, not a crystal ball."""

    name = "fade"

    def decide(self, opportunities: Sequence[Opportunity], portfolio) -> Decision:
        limit = int(self.params.get("limit", 2))
        return self._take(opportunities, ("wide_spread",), limit=limit, reason="fade wide book")
