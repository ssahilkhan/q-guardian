from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import structlog

from q_guardian.observability.data import Metric
from q_guardian.observability.enums import ExporterType
from q_guardian.observability.exceptions import ExporterError
from q_guardian.utils.uuid_utils import generate_uuid

logger = structlog.get_logger("observability.exporters.prometheus")

_EXPORT_VERSION = "1.0.0"


class PrometheusExporter:
    name: str = "prometheus"
    exporter_type: ExporterType = ExporterType.PROMETHEUS

    def __init__(self, prefix: str = "q_guardian") -> None:
        self._prefix = prefix
        self._logger = logger.bind(exporter=self.name, prefix=prefix)

    def export_metrics(self, metrics: list[Metric]) -> str:
        try:
            lines: list[str] = []
            lines.append(f"# Exported at {datetime.now(UTC).isoformat()}")
            lines.append("")
            for metric in metrics:
                sanitized_name = self._sanitize_name(metric.name)
                prefixed = f"{self._prefix}_{sanitized_name}"
                latest = metric.latest_value()
                labels = metric.labels
                if metric.description:
                    lines.append(f"# HELP {prefixed} {metric.description}")
                lines.append(f"# TYPE {prefixed} {metric.metric_type.value}")
                if latest is not None:
                    label_str = self._format_labels(labels) if labels else ""
                    lines.append(f"{prefixed}{label_str} {latest}")
                for point in metric.points:
                    merged = {**labels, **point.labels}
                    label_str = self._format_labels(merged) if merged else ""
                    lines.append(f"{prefixed}{label_str} {point.value}")
                lines.append("")
            result = "\n".join(lines).strip()
            self._logger.debug(
                "prometheus_export_completed",
                metric_count=len(metrics),
                size=len(result),
            )
            return result
        except ExporterError:
            raise
        except Exception as exc:
            self._logger.error("prometheus_export_failed", error=str(exc))
            raise ExporterError(
                message=f"Prometheus export failed: {exc}",
                details={"metric_count": len(metrics)},
            ) from exc

    def export_counter(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> str:
        try:
            sanitized = self._sanitize_name(name)
            prefixed = f"{self._prefix}_{sanitized}"
            label_str = self._format_labels(labels) if labels else ""
            result = f"{prefixed}{label_str} {value}"
            self._logger.debug("counter_exported", name=prefixed, value=value)
            return result
        except Exception as exc:
            self._logger.error("counter_export_failed", error=str(exc))
            raise ExporterError(
                message=f"Counter export failed: {exc}",
                details={"name": name},
            ) from exc

    def export_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> str:
        try:
            sanitized = self._sanitize_name(name)
            prefixed = f"{self._prefix}_{sanitized}"
            label_str = self._format_labels(labels) if labels else ""
            result = f"{prefixed}{label_str} {value}"
            self._logger.debug("gauge_exported", name=prefixed, value=value)
            return result
        except Exception as exc:
            self._logger.error("gauge_export_failed", error=str(exc))
            raise ExporterError(
                message=f"Gauge export failed: {exc}",
                details={"name": name},
            ) from exc

    def export_histogram(
        self,
        name: str,
        values: list[float],
        labels: dict[str, str] | None = None,
    ) -> str:
        try:
            sanitized = self._sanitize_name(name)
            prefixed = f"{self._prefix}_{sanitized}"
            label_str = self._format_labels(labels) if labels else ""
            lines: list[str] = []
            count = len(values)
            total = sum(values)
            sorted_vals = sorted(values)
            buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
            cumulative = 0
            for bucket in buckets:
                cumulative += sum(1 for v in sorted_vals if v <= bucket)
                bucket_labels = {**(labels or {}), "le": str(bucket)}
                bucket_label_str = self._format_labels(bucket_labels)
                lines.append(f"{prefixed}_bucket{bucket_label_str} {cumulative}")
            inf_labels = {**(labels or {}), "le": "+Inf"}
            inf_label_str = self._format_labels(inf_labels)
            lines.append(f"{prefixed}_bucket{inf_label_str} {count}")
            sum_label_str = label_str
            lines.append(f"{prefixed}_sum{sum_label_str} {total}")
            count_label_str = label_str
            lines.append(f"{prefixed}_count{count_label_str} {count}")
            result = "\n".join(lines)
            self._logger.debug(
                "histogram_exported",
                name=prefixed,
                count=count,
                total=total,
            )
            return result
        except Exception as exc:
            self._logger.error("histogram_export_failed", error=str(exc))
            raise ExporterError(
                message=f"Histogram export failed: {exc}",
                details={"name": name, "value_count": len(values)},
            ) from exc

    def _format_labels(self, labels: dict[str, str]) -> str:
        if not labels:
            return ""
        parts = [f'{k}="{v}"' for k, v in sorted(labels.items())]
        return "{" + ",".join(parts) + "}"

    def _sanitize_name(self, name: str) -> str:
        sanitized = re.sub(r"[.\-]", "_", name)
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", sanitized)
        sanitized = re.sub(r"_+", "_", sanitized)
        sanitized = sanitized.strip("_")
        return sanitized

    def parse_exposition(self, text: str) -> dict[str, Any]:
        try:
            result: dict[str, Any] = {}
            current_help: str | None = None
            current_type: str | None = None
            for line in text.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("# HELP"):
                    parts = line.split(" ", 3)
                    if len(parts) >= 4:
                        metric_name = parts[2]
                        current_help = parts[3]
                        if metric_name not in result:
                            result[metric_name] = {
                                "help": current_help,
                                "type": None,
                                "samples": [],
                            }
                        else:
                            result[metric_name]["help"] = current_help
                elif line.startswith("# TYPE"):
                    parts = line.split(" ", 3)
                    if len(parts) >= 4:
                        metric_name = parts[2]
                        current_type = parts[3]
                        if metric_name not in result:
                            result[metric_name] = {
                                "help": None,
                                "type": current_type,
                                "samples": [],
                            }
                        else:
                            result[metric_name]["type"] = current_type
                elif not line.startswith("#"):
                    match = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)\{([^}]*)\}\s+(.+)$", line)
                    if match:
                        metric_name = match.group(1)
                        labels_raw = match.group(2)
                        value_str = match.group(3)
                        labels = {}
                        if labels_raw:
                            for pair in labels_raw.split(","):
                                k, v = pair.split("=", 1)
                                labels[k.strip()] = v.strip().strip('"')
                        if metric_name not in result:
                            result[metric_name] = {
                                "help": None,
                                "type": None,
                                "samples": [],
                            }
                        result[metric_name]["samples"].append({
                            "labels": labels,
                            "value": float(value_str),
                        })
                    else:
                        match_simple = re.match(
                            r"^([a-zA-Z_:][a-zA-Z0-9_:]*)\s+(.+)$", line
                        )
                        if match_simple:
                            metric_name = match_simple.group(1)
                            value_str = match_simple.group(2)
                            if metric_name not in result:
                                result[metric_name] = {
                                    "help": None,
                                    "type": None,
                                    "samples": [],
                                }
                            result[metric_name]["samples"].append({
                                "labels": {},
                                "value": float(value_str),
                            })
            self._logger.debug(
                "exposition_parsed",
                metric_count=len(result),
            )
            return result
        except Exception as exc:
            self._logger.error("parse_exposition_failed", error=str(exc))
            raise ExporterError(
                message=f"Failed to parse Prometheus exposition: {exc}",
            ) from exc
