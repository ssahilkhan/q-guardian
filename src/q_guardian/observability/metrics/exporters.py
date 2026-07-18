"""MetricExporter base class and in-memory export implementations."""

from __future__ import annotations

import csv
import io
import json
from abc import ABC, abstractmethod
from typing import Any

import structlog

from q_guardian.observability.data import Metric
from q_guardian.observability.enums import ExporterType
from q_guardian.utils.datetime_utils import get_utc_now

logger = structlog.get_logger("observability.metrics.exporters")


class MetricExporter(ABC):
    """Abstract base class for metric exporters."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def exporter_type(self) -> ExporterType: ...

    @abstractmethod
    def export(self, metrics: list[Metric]) -> None: ...


class JsonMetricExporter(MetricExporter):
    """Exports metrics as JSON-formatted strings."""

    def __init__(self) -> None:
        self._last_output: str = ""

    @property
    def name(self) -> str:
        return "json"

    @property
    def exporter_type(self) -> ExporterType:
        return ExporterType.JSON

    def export(self, metrics: list[Metric]) -> None:
        payload = self._build_payload(metrics)
        self._last_output = json.dumps(payload, indent=2, default=str)
        logger.debug("json_export_completed", metric_count=len(metrics), size=len(self._last_output))

    def _build_payload(self, metrics: list[Metric]) -> dict[str, Any]:
        return {
            "exported_at": get_utc_now().isoformat(),
            "exporter": self.name,
            "metric_count": len(metrics),
            "metrics": [self._serialize_metric(m) for m in metrics],
        }

    def _serialize_metric(self, metric: Metric) -> dict[str, Any]:
        return {
            "metric_id": metric.metric_id,
            "name": metric.name,
            "metric_type": metric.metric_type.value,
            "unit": metric.unit.value,
            "description": metric.description,
            "labels": metric.labels,
            "points": [
                {
                    "timestamp": p.timestamp.isoformat(),
                    "value": p.value,
                    "labels": p.labels,
                }
                for p in metric.points
            ],
        }

    @property
    def last_output(self) -> str:
        return self._last_output


class CsvMetricExporter(MetricExporter):
    """Exports metrics as CSV-formatted strings."""

    def __init__(self) -> None:
        self._last_output: str = ""

    @property
    def name(self) -> str:
        return "csv"

    @property
    def exporter_type(self) -> ExporterType:
        return ExporterType.CSV

    def export(self, metrics: list[Metric]) -> None:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "metric_id",
            "name",
            "metric_type",
            "unit",
            "timestamp",
            "value",
            "labels",
        ])
        for metric in metrics:
            for point in metric.points:
                writer.writerow([
                    metric.metric_id,
                    metric.name,
                    metric.metric_type.value,
                    metric.unit.value,
                    point.timestamp.isoformat(),
                    point.value,
                    json.dumps(point.labels, default=str),
                ])
        self._last_output = output.getvalue()
        logger.debug("csv_export_completed", metric_count=len(metrics), size=len(self._last_output))

    @property
    def last_output(self) -> str:
        return self._last_output
