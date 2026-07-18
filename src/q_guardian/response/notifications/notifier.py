"""Notification Notifier — base notifier and routing."""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.response.data import NotificationRecord
from q_guardian.response.enums import NotificationChannel, NotificationPriority
from q_guardian.response.exceptions import NotificationError

logger = structlog.get_logger(__name__)


class Notifier:
    """Routes notifications to the appropriate channel handler."""

    def __init__(self) -> None:
        self._handlers: dict[NotificationChannel, Any] = {}
        self._sent: list[NotificationRecord] = []

    def register_handler(self, channel: NotificationChannel, handler: Any) -> None:
        """Register a handler for a notification channel."""
        self._handlers[channel] = handler

    def send(
        self,
        channel: NotificationChannel,
        recipients: list[str],
        subject: str,
        body: str,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        metadata: dict[str, Any] | None = None,
    ) -> NotificationRecord:
        """Send a notification through the given channel."""
        handler = self._handlers.get(channel)
        if handler is None:
            logger.warning("no_handler_for_channel", channel=channel.value)
            # Still record the notification
            record = NotificationRecord(
                channel=channel,
                recipients=recipients,
                subject=subject,
                body=body,
                priority=priority,
                metadata=metadata or {},
                error=f"No handler registered for channel {channel.value}",
            )
            self._sent.append(record)
            return record

        record = NotificationRecord(
            channel=channel,
            recipients=recipients,
            subject=subject,
            body=body,
            priority=priority,
            metadata=metadata or {},
        )

        try:
            handler.send_notification(recipients, subject, body, priority)
            record.status = "sent"
        except Exception as e:
            record.status = "failed"
            record.error = str(e)
            logger.error("notification_failed", channel=channel.value, error=str(e))

        self._sent.append(record)
        return record

    def get_sent(self) -> list[NotificationRecord]:
        return list(self._sent)

    def get_handler(self, channel: NotificationChannel) -> Any | None:
        return self._handlers.get(channel)
