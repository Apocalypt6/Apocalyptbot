"""Data API — trades, positions, holders. No auth."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .http import Http
from .models import Print

DATA = "https://data-api.polymarket.com"


class Tape:
    def __init__(self, http: Optional[Http] = None):
        self.http = http or Http()

    def trades(
        self,
        *,
        limit: int = 100,
        user: Optional[str] = None,
        market: Optional[str] = None,
        min_usd: Optional[float] = None,
        taker_only: bool = False,
    ) -> List[Print]:
        params: Dict[str, Any] = {"limit": min(limit, 500), "takerOnly": str(taker_only).lower()}
        if user:
            params["user"] = user
        if market:
            params["market"] = market
        if min_usd and min_usd > 0:
            params["filterType"] = "CASH"
            params["filterAmount"] = min_usd
        data = self.http.get(f"{DATA}/trades", params=params)
        rows = data if isinstance(data, list) else []
        prints = [Print.from_api(row) for row in rows if isinstance(row, dict)]
        if min_usd:
            prints = [p for p in prints if p.usd >= min_usd]
        return prints

    def positions(self, user: str, limit: int = 200) -> List[Dict[str, Any]]:
        data = self.http.get(f"{DATA}/positions", params={"user": user, "limit": limit})
        return data if isinstance(data, list) else []

    def holders(self, market: str) -> List[Dict[str, Any]]:
        data = self.http.get(f"{DATA}/holders", params={"market": market})
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("holders") or data.get("data") or []
        return []

    def value(self, user: str) -> Any:
        return self.http.get(f"{DATA}/value", params={"user": user})
