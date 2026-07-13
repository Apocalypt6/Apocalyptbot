"""Best-effort notifications for unattended (VPS) operation.

Sends short messages to Telegram and/or a generic webhook (Discord/Slack)
so you know when the bot trades, starts, or hits an error while you're not
watching. Everything here is *best-effort*: a failed notification is logged
but never raised into the trading loop, and if no channel is configured the
notifier is simply a no-op.

Configuration is via environment variables (never committed):
    APOCALYPTBOT_TELEGRAM_TOKEN   + APOCALYPTBOT_TELEGRAM_CHAT_ID
    APOCALYPTBOT_WEBHOOK_URL      (Discord or Slack incoming webhook)
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

if TYPE_CHECKING:  # avoid an import cycle; only needed for type hints
    from .broker import Fill

logger = logging.getLogger("apocalyptbot.notify")


class Notifier:
    """Fan out short text messages to configured channels, best-effort."""

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

    def send(self, text: str) -> bool:
        """Send ``text`` to every configured channel. Returns True if any succeeded."""
        if not self.enabled:
            return False
        if requests is None and self._session is None:  # pragma: no cover
            logger.warning("notifications configured but 'requests' is not installed")
            return False

        sess = self._session or requests
        ok = False
        for url, payload in self._targets(text):
            try:
                resp = sess.post(url, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                ok = True
            except Exception:  # noqa: BLE001 - never let notifications break trading
                logger.warning("notification to %s failed", _redact(url), exc_info=True)
        return ok

    def _targets(self, text: str) -> List[tuple]:
        targets: List[tuple] = []
        if self.telegram_token and self.telegram_chat_id:
            targets.append((
                f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                {"chat_id": self.telegram_chat_id, "text": text},
            ))
        if self.webhook_url:
            # "content" satisfies Discord, "text" satisfies Slack; each ignores the other.
            targets.append((self.webhook_url, {"content": text, "text": text}))
        return targets

    # --- convenience wrappers ---------------------------------------------

    def notify_fill(self, fill: "Fill") -> bool:
        emoji = "🟢" if fill.side == "BUY" else "🔴"
        pnl = f" | realized PnL {fill.realized_pnl:+.2f}" if fill.side == "SELL" else ""
        return self.send(
            f"{emoji} {fill.side} {fill.quantity:.8f} {fill.symbol} @ {fill.price:.2f}"
            f" (fee {fill.fee:.2f}){pnl} | cash {fill.cash_after:.2f}"
        )

    def notify_error(self, context: str, exc: BaseException) -> bool:
        return self.send(f"⚠️ Apocalyptbot error in {context}: {type(exc).__name__}: {exc}")


def _redact(url: str) -> str:
    """Hide the Telegram bot token when logging a failed URL."""
    if "/bot" in url:
        head, _, tail = url.partition("/bot")
        return f"{head}/bot<redacted>/{tail.split('/', 1)[-1] if '/' in tail else ''}"
    return url
