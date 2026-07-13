"""Market data: fetching, loading, saving, and a synthetic generator.

The default live source is Coinbase's public Exchange API, which needs no
account or API key for candle/price reads. Everything is normalized into a
list of :class:`Candle` sorted oldest-first, so strategies and the backtester
never care where the data came from.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from typing import Iterable, List, Optional

try:  # requests is only needed for live fetching, not for backtests on CSV.
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


class DataError(Exception):
    """Raised when market data cannot be fetched or parsed."""


@dataclass(frozen=True)
class Candle:
    """A single OHLCV bar. ``timestamp`` is the bar's open time (unix seconds)."""

    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def closes_key(self) -> float:
        return self.close


def closes(candles: Iterable[Candle]) -> List[float]:
    """Extract the close price series."""
    return [c.close for c in candles]


# Coinbase granularity is expressed in seconds; map friendly names to it.
_COINBASE_GRANULARITY = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "6h": 21600,
    "1d": 86400,
}


class CoinbaseData:
    """Thin client for Coinbase's public candle/price endpoints (no key needed)."""

    def __init__(self, base_url: str = "https://api.exchange.coinbase.com", session=None, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session

    def _get(self, path: str, params: Optional[dict] = None):
        if requests is None:
            raise DataError("The 'requests' package is required for live data. pip install requests")
        sess = self._session or requests
        url = f"{self.base_url}{path}"
        try:
            resp = sess.get(url, params=params, timeout=self.timeout, headers={"User-Agent": "apocalyptbot/0.1"})
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001 - surface a single clear error type
            raise DataError(f"request to {url} failed: {exc}") from exc

    def candles(self, product: str, interval: str = "1h", limit: int = 300) -> List[Candle]:
        """Fetch recent candles for ``product`` (e.g. 'BTC-USD').

        Coinbase caps a single request at 300 candles and returns them
        newest-first as [time, low, high, open, close, volume]. We normalize
        and sort oldest-first.
        """
        if interval not in _COINBASE_GRANULARITY:
            raise DataError(f"unsupported interval {interval!r}; choose from {sorted(_COINBASE_GRANULARITY)}")
        granularity = _COINBASE_GRANULARITY[interval]
        raw = self._get(f"/products/{product}/candles", params={"granularity": granularity})
        if not isinstance(raw, list):
            raise DataError(f"unexpected candle payload for {product}: {raw!r}")
        out = [
            Candle(
                timestamp=int(row[0]),
                low=float(row[1]),
                high=float(row[2]),
                open=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in raw
        ]
        out.sort(key=lambda c: c.timestamp)
        return out[-limit:] if limit else out

    def price(self, product: str) -> float:
        """Latest trade price for ``product``."""
        data = self._get(f"/products/{product}/ticker")
        try:
            return float(data["price"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DataError(f"could not read price for {product}: {data!r}") from exc


def save_csv(candles: List[Candle], path: str) -> None:
    """Persist candles to CSV (timestamp,open,high,low,close,volume)."""
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for c in candles:
            writer.writerow([c.timestamp, c.open, c.high, c.low, c.close, c.volume])


def load_csv(path: str) -> List[Candle]:
    """Load candles from a CSV produced by :func:`save_csv` (or compatible)."""
    out: List[Candle] = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            out.append(
                Candle(
                    timestamp=int(float(row["timestamp"])),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0) or 0),
                )
            )
    out.sort(key=lambda c: c.timestamp)
    return out


def synthetic(
    n: int = 500,
    start_price: float = 100.0,
    seed: int = 7,
    interval_seconds: int = 3600,
    drift: float = 0.0002,
    volatility: float = 0.02,
    start_ts: int = 1_600_000_000,
) -> List[Candle]:
    """Deterministic geometric-random-walk candles for tests and demos.

    Uses a self-contained LCG so results are reproducible without touching
    the global random state.
    """
    state = seed & 0xFFFFFFFF

    def rand() -> float:
        nonlocal state
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF  # in [0, 1)

    candles: List[Candle] = []
    price = start_price
    ts = start_ts
    for _ in range(n):
        # Box-Muller-ish shock from two uniforms -> roughly normal.
        u1 = max(rand(), 1e-9)
        u2 = rand()
        shock = math.sqrt(-2.0 * math.log(u1)) * math.cos(2 * math.pi * u2)
        ret = drift + volatility * shock
        open_p = price
        close_p = max(0.01, price * math.exp(ret))
        high_p = max(open_p, close_p) * (1 + volatility * rand() * 0.5)
        low_p = min(open_p, close_p) * (1 - volatility * rand() * 0.5)
        vol = 10 + rand() * 100
        candles.append(Candle(ts, open_p, high_p, low_p, close_p, vol))
        price = close_p
        ts += interval_seconds
    return candles
