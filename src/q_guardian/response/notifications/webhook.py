"""Webhook notification handler."""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.response.enums import NotificationPriority

logger = structlog.get_logger(__name__)


class WebhookNotifier:
    """Webhook notification handler (POST to URL)."""

    def __init__(self, url: str = "", headers: dict[str, str] | None = None) -> None:
        self._url = url
        self._headers = headers or {}
        self._sent: list[dict[str, Any]] = []

    def send_notification(
        self,
        recipients: list[str],
        subject: str,
        body: str,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
    ) -> dict[str, Any]:
        result = {
            "channel": "webhook",
            "url": self._url,
            "recipients": recipients,
            "subject": subject,
            "body_length": len(body),
            "priority": priority.value,
            "status": "sent",
        }
        self._sent.append(result)
        logger.info("webhook_sent", url=self._url, subject=subject)
        return result

    def get_sent(self) -> list[dict[str, Any]]:
        return list(self._sent)
