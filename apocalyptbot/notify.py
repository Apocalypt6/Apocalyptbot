"""Best-effort Telegram / webhook pings. Never break the hunt loop."""

from __future__ import annotations

import logging
import os
from typing import Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

from .broker import Fill

logger = logging.getLogger("apocalyptbot.notify")


class Notifier:
    def __init__(
        self,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        webhook_url: Optional[str] = None,
        session=None,
        timeout: float = 10.0,
    ):
        self.telegram_token = telegram_token or None
        self.telegram_chat_id = telegram_chat_id or None
        self.webhook_url = webhook_url or None
        self._session = session
        self.timeout = timeout

    @classmethod
    def from_env(cls, env=None) -> "Notifier":
        env = env if env is not None else os.environ
        return cls(
            telegram_token=env.get("APOCALYPTBOT_TELEGRAM_TOKEN"),
            telegram_chat_id=env.get("APOCALYPTBOT_TELEGRAM_CHAT_ID"),
            webhook_url=env.get("APOCALYPTBOT_WEBHOOK_URL"),
        )

    @property
    def enabled(self) -> bool:
        return bool((self.telegram_token and self.telegram_chat_id) or self.webhook_url)

    def _session_or_requests(self):
        if self._session is not None:
            return self._session
        if requests is None:
            return None
        return requests

    def send(self, text: str) -> bool:
        if not self.enabled:
            return False
        sess = self._session_or_requests()
        if sess is None:
            return False
        ok = False
        try:
            if self.telegram_token and self.telegram_chat_id:
                url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
                sess.post(
                    url,
                    json={"chat_id": self.telegram_chat_id, "text": text},
                    timeout=self.timeout,
                ).raise_for_status()
                ok = True
            if self.webhook_url:
                sess.post(
                    self.webhook_url,
                    json={"content": text, "text": text},
                    timeout=self.timeout,
                ).raise_for_status()
                ok = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("notify failed: %s", exc)
            return False
        return ok

    def notify_fill(self, fill: Fill) -> bool:
        pnl = f"  PnL {fill.realized_pnl:+.2f}" if fill.realized_pnl else ""
        body = (
            f"{fill.side} {fill.shares:.2f} {fill.outcome or fill.symbol} "
            f"@ {fill.price:.4f}  fee {fill.fee:.4f}  cash {fill.cash_after:.2f}{pnl}"
        )
        return self.send(body)
