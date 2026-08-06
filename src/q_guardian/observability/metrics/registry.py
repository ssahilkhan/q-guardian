"""MetricRegistry for dynamic registration of collectors and exporters."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from q_guardian.observability.exceptions import MetricError

if TYPE_CHECKING:
    from q_guardian.observability.metrics.collectors import MetricCollector
    from q_guardian.observability.metrics.exporters import MetricExporter

logger = structlog.get_logger("observability.metrics.registry")


class MetricRegistry:
    """Central registry for metric collectors and exporters.

    Supports dynamic registration and unregistration of collectors
    and exporters at runtime.
    """

    def __init__(self) -> None:
        self._collectors: dict[str, MetricCollector] = {}
        self._exporters: dict[str, MetricExporter] = {}

    def register_collector(self, collector: MetricCollector) -> None:
        if collector.name in self._collectors:
            raise MetricError(
                message=f"Collector '{collector.name}' is already registered",
                details={"collector_name": collector.name},
            )
        self._collectors[collector.name] = collector
        logger.info("collector_registered", name=collector.name)

    def unregister_collector(self, name: str) -> bool:
        removed = self._collectors.pop(name, None)
        if removed is not None:
            logger.info("collector_unregistered", name=name)
            return True
        return False

    def get_collector(self, name: str) -> MetricCollector | None:
        return self._collectors.get(name)

    def list_collectors(self) -> list[MetricCollector]:
        return list(self._collectors.values())

    def register_exporter(self, exporter: MetricExporter) -> None:
        if exporter.name in self._exporters:
            raise MetricError(
                message=f"Exporter '{exporter.name}' is already registered",
                details={"exporter_name": exporter.name},
            )
        self._exporters[exporter.name] = exporter
        logger.info(
            "exporter_registered", name=exporter.name, exporter_type=exporter.exporter_type.value
        )

    def unregister_exporter(self, name: str) -> bool:
        removed = self._exporters.pop(name, None)
        if removed is not None:
            logger.info("exporter_unregistered", name=name)
            return True
        return False

    def get_exporter(self, name: str) -> MetricExporter | None:
        return self._exporters.get(name)

    def list_exporters(self) -> list[MetricExporter]:
        return list(self._exporters.values())

    def to_dict(self) -> dict[str, dict[str, str]]:
        return {
            "collectors": {name: c.name for name, c in self._collectors.items()},
            "exporters": {name: e.name for name, e in self._exporters.items()},
        }
