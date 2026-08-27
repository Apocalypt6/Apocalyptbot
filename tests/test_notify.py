"""Best-effort Telegram / webhook pings. Fake session only — no network."""

from apocalyptbot.broker import Fill
from apocalyptbot.notify import Notifier
from tests.conftest import FakeSession


def test_disabled_notifier_is_noop():
    n = Notifier()
    assert n.enabled is False
    assert n.send("hello") is False


def test_from_env_reads_channels():
    env = {
        "APOCALYPTBOT_TELEGRAM_TOKEN": "tok",
        "APOCALYPTBOT_TELEGRAM_CHAT_ID": "123",
        "APOCALYPTBOT_WEBHOOK_URL": "https://example.test/hook",
    }
    n = Notifier.from_env(env)
    assert n.enabled is True
    assert n.telegram_token == "tok"
    assert n.telegram_chat_id == "123"
    assert n.webhook_url == "https://example.test/hook"


def test_from_env_empty_is_disabled():
    n = Notifier.from_env({})
    assert n.enabled is False


def test_webhook_send_posts_content_and_text():
    sess = FakeSession()
    n = Notifier(webhook_url="https://example.test/hook", session=sess)
    assert n.enabled is True
    assert n.send("hi") is True
    assert len(sess.calls) == 1
    assert sess.calls[0]["url"] == "https://example.test/hook"
    assert sess.calls[0]["json"]["content"] == "hi"
    assert sess.calls[0]["json"]["text"] == "hi"
    assert sess.calls[0]["timeout"] is not None


def test_telegram_and_webhook_both_targeted():
    sess = FakeSession()
    n = Notifier(
        telegram_token="tok",
        telegram_chat_id="123",
        webhook_url="https://ex.test/h",
        session=sess,
    )
    assert n.send("x") is True
    urls = [c["url"] for c in sess.calls]
    assert any("api.telegram.org" in u for u in urls)
    assert any(u.endswith("/bottok/sendMessage") or "bottok" in u for u in urls)
    assert "https://ex.test/h" in urls
    hook = next(c for c in sess.calls if c["url"] == "https://ex.test/h")
    assert hook["json"]["content"] == "x"
    assert hook["json"]["text"] == "x"
    tg = next(c for c in sess.calls if "api.telegram.org" in c["url"])
    assert tg["json"]["chat_id"] == "123"
    assert tg["json"]["text"] == "x"


def test_send_failure_is_swallowed():
    n = Notifier(webhook_url="https://example.test/hook", session=FakeSession(fail=True))
    assert n.send("hi") is False


def test_notify_fill_formats_side_and_symbol():
    sess = FakeSession()
    n = Notifier(webhook_url="https://example.test/hook", session=sess)
    fill = Fill(
        token_id="tok-yes",
        side="SELL",
        price=0.60,
        shares=10.0,
        fee=0.1,
        ts=1,
        cash_after=5_000.0,
        realized_pnl=123.45,
        market="will-x-happen",
        outcome="Yes",
    )
    assert n.notify_fill(fill) is True
    body = sess.calls[0]["json"]["content"]
    assert "SELL" in body
    assert "Yes" in body or "will-x-happen" in body or fill.symbol in body
    assert "PnL" in body
    assert sess.calls[0]["json"]["text"] == body
