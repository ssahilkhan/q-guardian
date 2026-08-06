"""Alert notifiers for Q-Guardian Observability."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable

    from q_guardian.observability.data import Alert

logger = structlog.get_logger(__name__)


class AlertNotifier(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def notify(self, alert: Alert) -> bool: ...


class LogNotifier(AlertNotifier):
    @property
    def name(self) -> str:
        return "log"

    def notify(self, alert: Alert) -> bool:
        logger.warning(
            "alert_notification",
            alert_id=alert.alert_id,
            rule_id=alert.rule_id,
            rule_name=alert.rule_name,
            severity=alert.severity.value,
            state=alert.state.value,
            message=alert.message,
        )
        return True


class WebhookNotifier(AlertNotifier):
    def __init__(self, url: str = "", headers: dict[str, str] | None = None) -> None:
        self._url = url
        self._headers = headers or {}
        self._payloads: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "webhook"

    def notify(self, alert: Alert) -> bool:
        payload = alert.model_dump(mode="json")
        self._payloads.append(payload)
        logger.info(
            "webhook_notification_sent",
            alert_id=alert.alert_id,
            url=self._url,
        )
        return True

    @property
    def payloads(self) -> list[dict[str, Any]]:
        return list(self._payloads)


class CallbackNotifier(AlertNotifier):
    def __init__(self, callback: Callable[[Alert], bool]) -> None:
        self._callback = callback

    @property
    def name(self) -> str:
        return "callback"

    def notify(self, alert: Alert) -> bool:
        try:
            result = self._callback(alert)
            logger.info(
                "callback_notification_completed",
                alert_id=alert.alert_id,
                success=result,
            )
            return result
        except Exception as e:
            logger.error(
                "callback_notification_failed",
                alert_id=alert.alert_id,
                error=str(e),
            )
            return False
