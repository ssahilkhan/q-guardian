"""Integration Cortex — TheHive/Cortex integration."""

from __future__ import annotations

from typing import Any

import structlog

from q_guardian.response.data import IntegrationConfig, IntegrationResult
from q_guardian.response.enums import IntegrationType

logger = structlog.get_logger(__name__)


class CortexIntegration:
    """TheHive/Cortex integration for case management."""

    def __init__(self, config: IntegrationConfig | None = None) -> None:
        self._config = config or IntegrationConfig(
            integration_type=IntegrationType.CORTEX_XSOAR,
            name="cortex",
            enabled=True,
        )
        self._results: list[IntegrationResult] = []

    def create_case(
        self,
        title: str,
        severity: int,
        description: str = "",
        correlation_id: str = "",
        **kwargs: Any,
    ) -> IntegrationResult:
        result = IntegrationResult(
            integration_type=IntegrationType.CORTEX_XSOAR,
            status="sent",
            correlation_id=correlation_id,
            response={"title": title, "severity": severity},
            metadata={"description": description, **kwargs},
        )
        self._results.append(result)
        logger.info("cortex_case_created", title=title, severity=severity)
        return result

    def run_analyzer(
        self,
        analyzer_name: str,
        observable_type: str,
        observable_value: str,
        correlation_id: str = "",
    ) -> IntegrationResult:
        result = IntegrationResult(
            integration_type=IntegrationType.CORTEX_XSOAR,
            status="sent",
            correlation_id=correlation_id,
            response={"analyzer": analyzer_name, "observable_type": observable_type},
            metadata={"observable_value": observable_value},
        )
        self._results.append(result)
        logger.info("cortex_analyzer_run", analyzer=analyzer_name)
        return result

    def get_results(self) -> list[IntegrationResult]:
        return list(self._results)
