"""Integration QRadar — IBM QRadar SIEM integration."""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.response.data import IntegrationConfig, IntegrationResult
from q_guardian.response.enums import IntegrationType

logger = structlog.get_logger(__name__)


class QRadarIntegration:
    """IBM QRadar integration."""

    def __init__(self, config: IntegrationConfig | None = None) -> None:
        self._config = config or IntegrationConfig(
            integration_type=IntegrationType.QRADAR,
            name="qradar",
            enabled=True,
        )
        self._results: list[IntegrationResult] = []

    def send_offense(
        self,
        description: str,
        severity: int,
        correlation_id: str = "",
        **kwargs: Any,
    ) -> IntegrationResult:
        result = IntegrationResult(
            integration_type=IntegrationType.QRADAR,
            status="sent",
            correlation_id=correlation_id,
            response={"description": description, "severity": severity},
            metadata=kwargs,
        )
        self._results.append(result)
        logger.info("qradar_offense_sent", severity=severity)
        return result

    def send_event(
        self,
        event_name: str,
        payload: dict[str, Any],
        correlation_id: str = "",
    ) -> IntegrationResult:
        result = IntegrationResult(
            integration_type=IntegrationType.QRADAR,
            status="sent",
            correlation_id=correlation_id,
            response={"event_name": event_name},
            metadata={"payload_keys": list(payload.keys())},
        )
        self._results.append(result)
        logger.info("qradar_event_sent", event_name=event_name)
        return result

    def get_results(self) -> list[IntegrationResult]:
        return list(self._results)
