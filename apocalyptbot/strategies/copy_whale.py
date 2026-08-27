from __future__ import annotations

from typing import Sequence

from ..models import Opportunity
from .base import Decision, Strategy


class CopyWhale(Strategy):
    """Copy large prints. Whales are wrong constantly."""

    name = "copy_whale"

    def decide(self, opportunities: Sequence[Opportunity], portfolio) -> Decision:
        limit = int(self.params.get("limit", 1))
        return self._take(opportunities, ("whale",), limit=limit, reason="copy whale")
