"""Notifier — manages notifications across channels."""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.risk.data import Notification
from q_guardian.risk.enums import Severity

logger = structlog.get_logger("risk.notifier")


class Notifier:
    """Manages notification dispatch across channels.

    Collects notifications and provides a simple interface for
    sending them. In production, channels would connect to
    external services (email, Slack, PagerDuty, etc.).
    """

    def __init__(self) -> None:
        self._notifications: list[Notification] = []
        self._channels: dict[str, bool] = {"default": True, "alert": True, "escalation": True}

    @property
    def notification_count(self) -> int:
        return len(self._notifications)

    def send(self, notification: Notification) -> bool:
        """Send a notification.

        Args:
            notification: The notification to send.

        Returns:
            True if the notification was sent successfully.
        """
        channel = notification.channel
        if channel not in self._channels or not self._channels[channel]:
            logger.warning("notification_channel_disabled", channel=channel)
            return False

        notification.sent = True
        self._notifications.append(notification)

        logger.info(
            "notification_sent",
            notification_id=notification.notification_id,
            title=notification.title,
            severity=notification.severity.value,
            channel=channel,
        )
        return True

    def send_alert(
        self,
        title: str,
        message: str,
        severity: Severity = Severity.MEDIUM,
        recipient: str = "admin",
    ) -> Notification:
        """Convenience method to send an alert."""
        notification = Notification(
            title=title,
            message=message,
            severity=severity,
            recipient=recipient,
            channel="alert",
        )
        self.send(notification)
        return notification

    def get_notifications(
        self,
        channel: str | None = None,
        severity: Severity | None = None,
    ) -> list[Notification]:
        """Get notifications, optionally filtered."""
        result = self._notifications
        if channel is not None:
            result = [n for n in result if n.channel == channel]
        if severity is not None:
            result = [n for n in result if n.severity == severity]
        return result

    def enable_channel(self, channel: str) -> None:
        """Enable a notification channel."""
        self._channels[channel] = True

    def disable_channel(self, channel: str) -> None:
        """Disable a notification channel."""
        self._channels[channel] = False

    def clear(self) -> None:
        """Clear all notifications."""
        self._notifications.clear()
