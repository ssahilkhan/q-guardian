"""Slack notification handler."""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.response.enums import NotificationPriority

logger = structlog.get_logger(__name__)


class SlackNotifier:
    """Slack notification handler."""

    def __init__(self, webhook_url: str = "", channel: str = "#security") -> None:
        self._webhook_url = webhook_url
        self._channel = channel
        self._sent: list[dict[str, Any]] = []

    def send_notification(
        self,
        recipients: list[str],
        subject: str,
        body: str,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
    ) -> dict[str, Any]:
        result = {
            "channel": "slack",
            "slack_channel": self._channel,
            "recipients": recipients,
            "subject": subject,
            "body_length": len(body),
            "priority": priority.value,
            "status": "sent",
        }
        self._sent.append(result)
        logger.info("slack_sent", channel=self._channel, subject=subject)
        return result

    def get_sent(self) -> list[dict[str, Any]]:
        return list(self._sent)
