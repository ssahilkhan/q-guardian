"""Tests for Notifications subsystem."""

from q_guardian.response.enums import NotificationChannel
from q_guardian.response.notifications.email import EmailNotifier
from q_guardian.response.notifications.notifier import Notifier
from q_guardian.response.notifications.slack import SlackNotifier
from q_guardian.response.notifications.teams import TeamsNotifier
from q_guardian.response.notifications.webhook import WebhookNotifier


class TestNotifier:
    def test_send_with_handler(self) -> None:
        n = Notifier()
        email = EmailNotifier()
        n.register_handler(NotificationChannel.EMAIL, email)
        record = n.send(
            NotificationChannel.EMAIL,
            recipients=["a@b.com"],
            subject="Alert",
            body="test body",
        )
        assert record.status == "sent"

    def test_send_without_handler(self) -> None:
        n = Notifier()
        record = n.send(
            NotificationChannel.SLACK,
            recipients=["#chan"],
            subject="Alert",
            body="body",
        )
        assert record.status == ""
        assert "No handler" in record.error

    def test_get_sent(self) -> None:
        n = Notifier()
        n.register_handler(NotificationChannel.EMAIL, EmailNotifier())
        n.send(NotificationChannel.EMAIL, ["a@b.com"], "s", "b")
        assert len(n.get_sent()) == 1

    def test_get_handler(self) -> None:
        n = Notifier()
        email = EmailNotifier()
        n.register_handler(NotificationChannel.EMAIL, email)
        assert n.get_handler(NotificationChannel.EMAIL) is email
        assert n.get_handler(NotificationChannel.SLACK) is None


class TestEmailNotifier:
    def test_send(self) -> None:
        e = EmailNotifier()
        result = e.send_notification(["a@b.com"], "subj", "body")
        assert result["status"] == "sent"
        assert len(e.get_sent()) == 1


class TestWebhookNotifier:
    def test_send(self) -> None:
        w = WebhookNotifier(url="https://example.com/hook")
        result = w.send_notification(["url1"], "subj", "body")
        assert result["status"] == "sent"
        assert result["url"] == "https://example.com/hook"


class TestSlackNotifier:
    def test_send(self) -> None:
        s = SlackNotifier(channel="#security")
        result = s.send_notification(["#ops"], "subj", "body")
        assert result["status"] == "sent"
        assert result["slack_channel"] == "#security"


class TestTeamsNotifier:
    def test_send(self) -> None:
        t = TeamsNotifier()
        result = t.send_notification(["team1"], "subj", "body")
        assert result["status"] == "sent"

    def test_get_sent(self) -> None:
        t = TeamsNotifier()
        t.send_notification(["team1"], "s", "b")
        assert len(t.get_sent()) == 1
