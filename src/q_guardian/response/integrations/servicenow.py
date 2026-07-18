"""Integration ServiceNow — ITSM integration."""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.response.data import IntegrationConfig, IntegrationResult
from q_guardian.response.enums import IntegrationType

logger = structlog.get_logger(__name__)


class ServiceNowIntegration:
    """ServiceNow ITSM integration for incident/change management."""

    def __init__(self, config: IntegrationConfig | None = None) -> None:
        self._config = config or IntegrationConfig(
            integration_type=IntegrationType.SERVICENOW,
            name="servicenow",
            enabled=True,
        )
        self._results: list[IntegrationResult] = []

    def create_incident(
        self,
        short_description: str,
        urgency: str = "medium",
        impact: str = "medium",
        correlation_id: str = "",
        **kwargs: Any,
    ) -> IntegrationResult:
        result = IntegrationResult(
            integration_type=IntegrationType.SERVICENOW,
            status="sent",
            correlation_id=correlation_id,
            response={
                "short_description": short_description,
                "urgency": urgency,
                "impact": impact,
            },
            metadata=kwargs,
        )
        self._results.append(result)
        logger.info("servicenow_incident_created", description=short_description)
        return result

    def create_change_request(
        self,
        short_description: str,
        risk: str = "low",
        correlation_id: str = "",
        **kwargs: Any,
    ) -> IntegrationResult:
        result = IntegrationResult(
            integration_type=IntegrationType.SERVICENOW,
            status="sent",
            correlation_id=correlation_id,
            response={"short_description": short_description, "risk": risk},
            metadata=kwargs,
        )
        self._results.append(result)
        logger.info("servicenow_change_created", description=short_description)
        return result

    def get_results(self) -> list[IntegrationResult]:
        return list(self._results)
