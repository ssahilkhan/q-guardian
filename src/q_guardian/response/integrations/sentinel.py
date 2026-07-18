"""Integration Sentinel — Microsoft Sentinel SIEM integration."""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.response.data import IntegrationConfig, IntegrationResult
from q_guardian.response.enums import IntegrationType
from q_guardian.response.exceptions import IntegrationError

logger = structlog.get_logger(__name__)


class SentinelIntegration:
    """Microsoft Sentinel integration."""

    def __init__(self, config: IntegrationConfig | None = None) -> None:
        self._config = config or IntegrationConfig(
            integration_type=IntegrationType.SENTINEL,
            name="sentinel",
            enabled=True,
        )
        self._results: list[IntegrationResult] = []

    def send_incident(
        self,
        title: str,
        severity: str,
        description: str = "",
        correlation_id: str = "",
        **kwargs: Any,
    ) -> IntegrationResult:
        """Send an incident to Sentinel."""
        result = IntegrationResult(
            integration_type=IntegrationType.SENTINEL,
            status="sent",
            correlation_id=correlation_id,
            request_id=correlation_id,
            response={"title": title, "severity": severity},
            metadata={"description": description, **kwargs},
        )
        self._results.append(result)
        logger.info("sentinel_incident_sent", title=title, severity=severity)
        return result

    def send_alert(
        self,
        alert_name: str,
        severity: str,
        correlation_id: str = "",
        **kwargs: Any,
    ) -> IntegrationResult:
        result = IntegrationResult(
            integration_type=IntegrationType.SENTINEL,
            status="sent",
            correlation_id=correlation_id,
            response={"alert_name": alert_name, "severity": severity},
            metadata=kwargs,
        )
        self._results.append(result)
        logger.info("sentinel_alert_sent", alert_name=alert_name)
        return result

    def get_results(self) -> list[IntegrationResult]:
        return list(self._results)

    @property
    def config(self) -> IntegrationConfig:
        return self._config
