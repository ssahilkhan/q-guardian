from __future__ import annotations

from collections import Counter
from typing import Any

import structlog

from q_guardian.observability.data import AnalyticsReport, TimeWindow

logger = structlog.get_logger("observability.analytics.reports")


class ReportGenerator:
    """Generator for analytics summary reports."""

    def __init__(self) -> None:
        logger.debug("report_generator_created")

    def generate_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        total_events = data.get("total_events", 0)
        summary["total_events"] = total_events
        summary["event_type_counts"] = data.get("event_type_counts", {})
        summary["time_range"] = data.get("time_range", {})
        if "metric_names" in data:
            summary["unique_metrics"] = len(data["metric_names"])
            summary["metric_names"] = data["metric_names"]
        if "sessions" in data:
            summary["total_sessions"] = len(data["sessions"])
        if "agents" in data:
            summary["unique_agents"] = len(data["agents"])
        summary["generated"] = True
        logger.debug("summary_generated", total_events=total_events)
        return summary

    def generate_threat_summary(
        self, threat_data: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not threat_data:
            return {
                "total_threats": 0,
                "threat_types": {},
                "average_confidence": 0.0,
                "severity_distribution": {},
            }
        total = len(threat_data)
        threat_types: Counter[str] = Counter()
        severities: Counter[str] = Counter()
        confidences: list[float] = []
        for threat in threat_data:
            threat_type = threat.get("type", threat.get("threat_type", "unknown"))
            threat_types[threat_type] += 1
            severity = threat.get("severity", "unknown")
            severities[severity] += 1
            confidence = threat.get("confidence", threat.get("confidence_score", 0.0))
            if isinstance(confidence, (int, float)):
                confidences.append(float(confidence))
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        result = {
            "total_threats": total,
            "threat_types": dict(threat_types),
            "average_confidence": avg_confidence,
            "severity_distribution": dict(severities),
        }
        logger.debug("threat_summary_generated", total_threats=total)
        return result

    def generate_performance_summary(
        self, perf_data: dict[str, Any]
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        latencies = perf_data.get("latencies", [])
        if latencies:
            numeric_latencies = [float(v) for v in latencies if isinstance(v, (int, float))]
            if numeric_latencies:
                sorted_lat = sorted(numeric_latencies)
                n = len(sorted_lat)
                summary["average_latency"] = sum(numeric_latencies) / n
                summary["median_latency"] = sorted_lat[n // 2]
                summary["p95_latency"] = sorted_lat[int(n * 0.95)] if n > 1 else sorted_lat[-1]
                summary["p99_latency"] = sorted_lat[int(n * 0.99)] if n > 1 else sorted_lat[-1]
                summary["min_latency"] = sorted_lat[0]
                summary["max_latency"] = sorted_lat[-1]
                summary["sample_count"] = n
        throughput = perf_data.get("throughput", [])
        if throughput:
            numeric_throughput = [float(v) for v in throughput if isinstance(v, (int, float))]
            if numeric_throughput:
                summary["average_throughput"] = sum(numeric_throughput) / len(numeric_throughput)
                summary["peak_throughput"] = max(numeric_throughput)
        summary["error_rate"] = perf_data.get("error_rate", 0.0)
        summary["success_rate"] = perf_data.get("success_rate", 1.0)
        logger.debug("performance_summary_generated")
        return summary

    def generate_health_summary(
        self, health_data: dict[str, Any]
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        components = health_data.get("components", [])
        summary["total_components"] = len(components)
        statuses: Counter[str] = Counter()
        scores: list[float] = []
        for comp in components:
            status = comp.get("status", "unknown")
            statuses[status] += 1
            score = comp.get("health_score", comp.get("score", 0.0))
            if isinstance(score, (int, float)):
                scores.append(float(score))
        summary["status_distribution"] = dict(statuses)
        if scores:
            summary["average_health_score"] = sum(scores) / len(scores)
            summary["min_health_score"] = min(scores)
            summary["max_health_score"] = max(scores)
        else:
            summary["average_health_score"] = 0.0
            summary["min_health_score"] = 0.0
            summary["max_health_score"] = 0.0
        summary["uptime_seconds"] = health_data.get("uptime_seconds", 0.0)
        summary["active_warnings"] = health_data.get("active_warnings", 0)
        summary["active_failures"] = health_data.get("active_failures", 0)
        logger.debug("health_summary_generated")
        return summary

    def format_report(self, report: AnalyticsReport) -> dict[str, Any]:
        formatted: dict[str, Any] = {
            "report_id": report.report_id,
            "title": report.title,
            "generated_at": report.generated_at.isoformat(),
            "time_window": None,
            "sections": {},
        }
        if report.time_window:
            formatted["time_window"] = {
                "start": report.time_window.start.isoformat(),
                "end": report.time_window.end.isoformat(),
                "duration_seconds": report.time_window.duration_seconds,
            }
        formatted["sections"]["threat_trends"] = [
            {
                "metric_name": t.metric_name,
                "direction": t.direction.value,
                "slope": t.slope,
                "r_squared": t.r_squared,
                "mean": t.mean,
                "std_dev": t.std_dev,
                "min_value": t.min_value,
                "max_value": t.max_value,
                "sample_count": t.sample_count,
            }
            for t in report.threat_trends
        ]
        formatted["sections"]["policy_trends"] = [
            {
                "metric_name": t.metric_name,
                "direction": t.direction.value,
                "slope": t.slope,
                "r_squared": t.r_squared,
                "mean": t.mean,
                "std_dev": t.std_dev,
                "min_value": t.min_value,
                "max_value": t.max_value,
                "sample_count": t.sample_count,
            }
            for t in report.policy_trends
        ]
        formatted["sections"]["risk_trends"] = [
            {
                "metric_name": t.metric_name,
                "direction": t.direction.value,
                "slope": t.slope,
                "r_squared": t.r_squared,
                "mean": t.mean,
                "std_dev": t.std_dev,
                "min_value": t.min_value,
                "max_value": t.max_value,
                "sample_count": t.sample_count,
            }
            for t in report.risk_trends
        ]
        formatted["sections"]["response_trends"] = [
            {
                "metric_name": t.metric_name,
                "direction": t.direction.value,
                "slope": t.slope,
                "r_squared": t.r_squared,
                "mean": t.mean,
                "std_dev": t.std_dev,
                "min_value": t.min_value,
                "max_value": t.max_value,
                "sample_count": t.sample_count,
            }
            for t in report.response_trends
        ]
        formatted["sections"]["provider_accuracy"] = report.provider_accuracy
        formatted["sections"]["plugin_usage"] = report.plugin_usage
        formatted["sections"]["quantum_usage"] = report.quantum_usage
        formatted["sections"]["fusion_strategy_usage"] = report.fusion_strategy_usage
        formatted["sections"]["average_confidence"] = report.average_confidence
        formatted["sections"]["top_threat_types"] = report.top_threat_types
        formatted["sections"]["top_policies"] = report.top_policies
        formatted["sections"]["most_active_sessions"] = report.most_active_sessions
        formatted["sections"]["most_active_agents"] = report.most_active_agents
        formatted["sections"]["forecasts"] = [
            {
                "metric_name": f.metric_name,
                "method": f.method,
                "confidence_level": f.confidence_level,
                "forecast_count": len(f.forecast_values),
            }
            for f in report.forecasts
        ]
        formatted["sections"]["summary"] = report.summary
        logger.debug("report_formatted", report_id=report.report_id)
        return formatted
