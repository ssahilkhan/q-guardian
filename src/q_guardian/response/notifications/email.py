"""Email notification handler."""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.response.enums import NotificationPriority

logger = structlog.get_logger(__name__)


class EmailNotifier:
    """Email notification handler (stub — send logic is integration-layer)."""

    def __init__(self, smtp_config: dict[str, Any] | None = None) -> None:
        self._config = smtp_config or {}
        self._sent: list[dict[str, Any]] = []

    def send_notification(
        self,
        recipients: list[str],
        subject: str,
        body: str,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
    ) -> dict[str, Any]:
        """Send an email notification."""
        result = {
            "channel": "email",
            "recipients": recipients,
            "subject": subject,
            "body_length": len(body),
            "priority": priority.value,
            "status": "sent",
        }
        self._sent.append(result)
        logger.info("email_sent", recipients=recipients, subject=subject)
        return result

    def get_sent(self) -> list[dict[str, Any]]:
        return list(self._sent)
