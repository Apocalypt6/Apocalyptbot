"""Gamma API — market / event discovery. No auth."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .http import Http
from .models import Market

GAMMA = "https://gamma-api.polymarket.com"


class Gamma:
    def __init__(self, http: Optional[Http] = None):
        self.http = http or Http()

    def events(
        self,
        *,
        active: bool = True,
        closed: bool = False,
        order: str = "volume24hr",
        ascending: bool = False,
        limit: int = 50,
        offset: int = 0,
        **extra: Any,
    ) -> List[Dict[str, Any]]:
        params = {
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "order": order,
            "ascending": str(ascending).lower(),
            "limit": limit,
            "offset": offset,
        }
        params.update(extra)
        data = self.http.get(f"{GAMMA}/events", params=params)
        return data if isinstance(data, list) else []

    def markets(
        self,
        *,
        active: bool = True,
        closed: bool = False,
        order: str = "volume24hr",
        ascending: bool = False,
        limit: int = 50,
        offset: int = 0,
        **extra: Any,
    ) -> List[Dict[str, Any]]:
        params = {
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "order": order,
            "ascending": str(ascending).lower(),
            "limit": limit,
            "offset": offset,
        }
        params.update(extra)
        data = self.http.get(f"{GAMMA}/markets", params=params)
        return data if isinstance(data, list) else []

    def market_by_slug(self, slug: str) -> Dict[str, Any]:
        data = self.http.get(f"{GAMMA}/markets/slug/{slug}")
        if not isinstance(data, dict):
            raise ValueError(f"no market for slug {slug!r}")
        return data

    def event_by_slug(self, slug: str) -> Dict[str, Any]:
        data = self.http.get(f"{GAMMA}/events/slug/{slug}")
        if not isinstance(data, dict):
            raise ValueError(f"no event for slug {slug!r}")
        return data

    def search(self, q: str, limit_per_type: int = 10) -> Dict[str, Any]:
        data = self.http.get(
            f"{GAMMA}/public-search",
            params={"q": q, "limit_per_type": limit_per_type},
        )
        return data if isinstance(data, dict) else {"events": []}

    def hot_markets(self, limit: int = 40) -> List[Market]:
        """Flatten the hottest events + standalone markets, unique by condition id."""
        seen: Dict[str, Market] = {}

        for event in self.events(limit=max(limit, 10)):
            nested = event.get("markets") or []
            for raw in nested:
                if not isinstance(raw, dict):
                    continue
                market = Market.from_gamma(raw, event)
                if not market.condition_id or market.closed or not market.token_ids():
                    continue
                seen[market.condition_id] = market

        if len(seen) < limit:
            for raw in self.markets(limit=limit):
                market = Market.from_gamma(raw)
                if not market.condition_id or market.closed or not market.token_ids():
                    continue
                seen.setdefault(market.condition_id, market)

        ranked = sorted(seen.values(), key=lambda m: m.volume_24h, reverse=True)
        return ranked[:limit]
