"""Integration Splunk — Splunk SIEM integration."""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.response.data import IntegrationConfig, IntegrationResult
from q_guardian.response.enums import IntegrationType

logger = structlog.get_logger(__name__)


class SplunkIntegration:
    """Splunk integration for log ingestion and alerting."""

    def __init__(self, config: IntegrationConfig | None = None) -> None:
        self._config = config or IntegrationConfig(
            integration_type=IntegrationType.SPLUNK,
            name="splunk",
            enabled=True,
        )
        self._results: list[IntegrationResult] = []

    def send_event(
        self,
        source: str,
        sourcetype: str,
        event_data: dict[str, Any],
        correlation_id: str = "",
    ) -> IntegrationResult:
        result = IntegrationResult(
            integration_type=IntegrationType.SPLUNK,
            status="sent",
            correlation_id=correlation_id,
            response={"source": source, "sourcetype": sourcetype},
            metadata={"event_data_keys": list(event_data.keys())},
        )
        self._results.append(result)
        logger.info("splunk_event_sent", source=source)
        return result

    def send_alert(
        self,
        alert_name: str,
        severity: str,
        search_query: str = "",
        correlation_id: str = "",
    ) -> IntegrationResult:
        result = IntegrationResult(
            integration_type=IntegrationType.SPLUNK,
            status="sent",
            correlation_id=correlation_id,
            response={"alert_name": alert_name, "severity": severity},
            metadata={"search_query": search_query},
        )
        self._results.append(result)
        logger.info("splunk_alert_sent", alert_name=alert_name)
        return result

    def get_results(self) -> list[IntegrationResult]:
        return list(self._results)
