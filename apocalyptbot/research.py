"""Paid web search is intentionally not on the hunt path.

Exa / similar APIs bill about $7 per 1k Instant searches. This module exists
so nobody "just wires it in" and wakes up to an empty free-tier balance.
Polymarket Gamma + CLOB + Data API are free and are what `scan`/`hunt` use.
"""

from __future__ import annotations

import os


class ResearchDisabled(RuntimeError):
    pass


def estimate_exa_cost(searches: int, extra_results: int = 0) -> float:
    """Ballpark Instant-tier cost. Not a billing API."""
    return searches * 0.007 + extra_results * 0.001


def run_research(query: str, budget_usd: float = 0.0) -> None:
    key = os.environ.get("EXA_API_KEY") or os.environ.get("EXASEARCH_API_KEY")
    if not key:
        raise ResearchDisabled(
            "research is off. Hunt uses free Polymarket APIs. "
            "If you really want paid search later, set EXA_API_KEY and pass --budget."
        )
    if budget_usd <= 0:
        raise ResearchDisabled(
            "research refused: --budget must be > 0. "
            f"One Instant search is ~${estimate_exa_cost(1):.3f}."
        )
    raise ResearchDisabled(
        "research is stubbed on purpose. Do not burn search credits from the hunt loop. "
        f"Query was {query!r}, budget ${budget_usd:.2f}."
    )
