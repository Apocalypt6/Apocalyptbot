from apocalyptbot.broker import Fill
from apocalyptbot.notify import Notifier


class FakeResponse:
    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json})
        if self.fail:
            raise RuntimeError("boom")
        return FakeResponse()


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


def test_webhook_send_posts_payload():
    sess = FakeSession()
    n = Notifier(webhook_url="https://example.test/hook", session=sess)
    assert n.send("hi") is True
    assert len(sess.calls) == 1
    assert sess.calls[0]["url"] == "https://example.test/hook"
    # Both Discord ("content") and Slack ("text") keys are present.
    assert sess.calls[0]["json"]["content"] == "hi"
    assert sess.calls[0]["json"]["text"] == "hi"


def test_telegram_and_webhook_both_targeted():
    sess = FakeSession()
    n = Notifier(telegram_token="tok", telegram_chat_id="123", webhook_url="https://ex.test/h", session=sess)
    n.send("x")
    urls = [c["url"] for c in sess.calls]
    assert any("api.telegram.org" in u for u in urls)
    assert "https://ex.test/h" in urls


def test_send_failure_is_swallowed():
    sess = FakeSession(fail=True)
    n = Notifier(webhook_url="https://example.test/hook", session=sess)
    # Should not raise even though the underlying post throws.
    assert n.send("hi") is False


def test_notify_fill_formats_message():
    sess = FakeSession()
    n = Notifier(webhook_url="https://example.test/hook", session=sess)
    fill = Fill("BTC-USD", "SELL", 50000.0, 0.1, 2.5, 1, cash_after=5000.0, realized_pnl=123.45)
    n.notify_fill(fill)
    body = sess.calls[0]["json"]["content"]
    assert "SELL" in body and "BTC-USD" in body and "PnL" in body
