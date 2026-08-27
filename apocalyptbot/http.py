"""Tiny HTTP helper with retries. Public Polymarket APIs only."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


class HttpError(Exception):
    """Network or non-2xx response from a Polymarket API."""


class Http:
    def __init__(
        self,
        timeout: float = 20.0,
        user_agent: str = "apocalyptbot/0.2",
        session=None,
        retries: int = 3,
        backoff: float = 0.6,
        sleeper=time.sleep,
    ):
        if session is None and requests is None:
            raise HttpError("the requests package is required")
        self.timeout = timeout
        self.user_agent = user_agent
        self.session = session if session is not None else requests.Session()
        self.retries = retries
        self.backoff = backoff
        self.sleeper = sleeper

    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request("GET", url, params=params)

    def post(self, url: str, payload: Any = None) -> Any:
        return self._request("POST", url, json=payload)

    def _request(self, method: str, url: str, **kwargs) -> Any:
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        last_exc: Optional[BaseException] = None
        for attempt in range(self.retries + 1):
            try:
                resp = self.session.request(
                    method,
                    url,
                    headers=headers,
                    timeout=self.timeout,
                    **kwargs,
                )
            except Exception as exc:  # noqa: BLE001 — surface as HttpError
                last_exc = exc
                if attempt >= self.retries:
                    raise HttpError(f"{method} {url} failed: {exc}") from exc
                self.sleeper(self.backoff * (attempt + 1))
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                last_exc = HttpError(f"{method} {url} -> {resp.status_code}")
                if attempt >= self.retries:
                    raise last_exc
                retry_after = resp.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after else self.backoff * (attempt + 1)
                except ValueError:
                    wait = self.backoff * (attempt + 1)
                self.sleeper(min(wait, 15.0))
                continue

            if resp.status_code >= 400:
                body = (resp.text or "")[:300]
                raise HttpError(f"{method} {url} -> {resp.status_code}: {body}")

            if not resp.content:
                return None
            try:
                return resp.json()
            except ValueError as exc:
                raise HttpError(f"{method} {url} returned non-JSON") from exc

        raise HttpError(f"{method} {url} failed: {last_exc}")
