from __future__ import annotations

import threading
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

import structlog

from q_guardian.observability.analytics.forecasting import ForecastEngine
from q_guardian.observability.analytics.reports import ReportGenerator
from q_guardian.observability.analytics.statistics import StatisticsEngine
from q_guardian.observability.analytics.trend_analysis import TrendAnalyzer
from q_guardian.observability.data import (
    AnalyticsReport,
    ForecastResult,
    MetricPoint,
    TimeWindow,
    TrendData,
)
from q_guardian.observability.enums import AnalyticsGranularity, TrendDirection
from q_guardian.observability.exceptions import AnalyticsError
from q_guardian.utils.uuid_utils import generate_uuid

logger = structlog.get_logger("observability.analytics.engine")


class AnalyticsEngine:
    """Main analytics engine for ingesting events, computing trends, and generating reports."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._lock = threading.RLock()
        self._initialized = False
        self._report_generator = ReportGenerator()
        self._trend_analyzer = TrendAnalyzer()
        self._statistics = StatisticsEngine()
        self._forecast_engine = ForecastEngine()
        self._events: list[dict[str, Any]] = []
        self._metric_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._threat_events: list[dict[str, Any]] = []
        self._policy_events: list[dict[str, Any]] = []
        self._risk_events: list[dict[str, Any]] = []
        self._response_events: list[dict[str, Any]] = []
        self._provider_events: list[dict[str, Any]] = []
        self._plugin_events: list[dict[str, Any]] = []
        self._quantum_events: list[dict[str, Any]] = []
        self._fusion_events: list[dict[str, Any]] = []
        self._session_events: list[dict[str, Any]] = []
        self._agent_events: list[dict[str, Any]] = []
        self._confidence_values: list[float] = []
        self._metric_points: dict[str, list[MetricPoint]] = defaultdict(list)
        self._granularity = self._config.get("granularity", AnalyticsGranularity.HOUR)

    def initialize(self) -> None:
        with self._lock:
            self._initialized = True
            logger.info(
                "analytics_engine_initialized",
                granularity=self._granularity.value,
            )

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise AnalyticsError(
                message="AnalyticsEngine has not been initialized",
                details={"hint": "Call initialize() first"},
            )

    def ingest_event(self, event: Any) -> None:
        with self._lock:
            self._ensure_initialized()
            event_dict: dict[str, Any]
            if isinstance(event, dict):
                event_dict = dict(event)
            else:
                event_dict = {
                    "type": type(event).__name__,
                    "data": event,
                }
            if "timestamp" not in event_dict:
                event_dict["timestamp"] = datetime.now(UTC).isoformat()
            event_dict.setdefault("event_id", generate_uuid())
            self._events.append(event_dict)
            event_type = str(event_dict.get("type", "")).lower()
            self._categorize_event(event_type, event_dict)
            logger.debug(
                "event_ingested",
                event_id=event_dict.get("event_id"),
                event_type=event_type,
            )

    def _categorize_event(self, event_type: str, event_dict: dict[str, Any]) -> None:
        if "threat" in event_type:
            self._threat_events.append(event_dict)
        if "policy" in event_type:
            self._policy_events.append(event_dict)
        if "risk" in event_type:
            self._risk_events.append(event_dict)
        if "response" in event_type:
            self._response_events.append(event_dict)
        if "provider" in event_type or "accuracy" in event_type:
            self._provider_events.append(event_dict)
        if "plugin" in event_type:
            self._plugin_events.append(event_dict)
        if "quantum" in event_type:
            self._quantum_events.append(event_dict)
        if "fusion" in event_type or "strategy" in event_type:
            self._fusion_events.append(event_dict)
        if "session" in event_type:
            self._session_events.append(event_dict)
        if "agent" in event_type:
            self._agent_events.append(event_dict)
        if "confidence" in event_dict:
            conf = event_dict.get("confidence")
            if isinstance(conf, (int, float)):
                self._confidence_values.append(float(conf))

    def record_metric_event(
        self,
        metric_name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        with self._lock:
            self._ensure_initialized()
            point = MetricPoint(value=value, labels=labels or {})
            self._metric_points[metric_name].append(point)
            logger.debug(
                "metric_event_recorded",
                metric_name=metric_name,
                value=value,
            )

    def generate_report(
        self, time_window: TimeWindow | None = None
    ) -> AnalyticsReport:
        with self._lock:
            self._ensure_initialized()
            effective_window = time_window or self._build_default_window()
            threat_trends = self.get_threat_trends(effective_window)
            policy_trends = self.get_policy_trends(effective_window)
            risk_trends = self.get_risk_trends(effective_window)
            response_trends = self.get_response_trends(effective_window)
            report = AnalyticsReport(
                title="Q-Guardian Analytics Report",
                time_window=effective_window,
                threat_trends=threat_trends,
                policy_trends=policy_trends,
                risk_trends=risk_trends,
                response_trends=response_trends,
                provider_accuracy=self.get_provider_accuracy(),
                plugin_usage=self.get_plugin_usage(),
                quantum_usage=self.get_quantum_usage(),
                fusion_strategy_usage=self.get_fusion_strategy_usage(),
                average_confidence=self.get_average_confidence(),
                top_threat_types=self.get_top_threat_types(),
                top_policies=self.get_top_policies(),
                most_active_sessions=self.get_most_active_sessions(),
                most_active_agents=self.get_most_active_agents(),
                summary={
                    "total_events": len(self._events),
                    "total_metrics": len(self._metric_points),
                    "granularity": self._granularity.value,
                },
            )
            logger.info(
                "analytics_report_generated",
                report_id=report.report_id,
                threat_trends=len(threat_trends),
                policy_trends=len(policy_trends),
                risk_trends=len(risk_trends),
                response_trends=len(response_trends),
            )
            return report

    def _build_default_window(self) -> TimeWindow:
        now = datetime.now(UTC)
        return TimeWindow(
            start=datetime(
                now.year, now.month, now.day, now.hour, tzinfo=UTC
            ),
            end=now,
        )

    def _extract_metric_values(
        self, events: list[dict[str, Any]], window: TimeWindow | None = None
    ) -> list[float]:
        values: list[float] = []
        for event in events:
            if window is not None:
                ts_str = event.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if not window.contains(ts):
                        continue
                except (ValueError, TypeError):
                    pass
            for key in ("value", "count", "confidence", "score", "metric"):
                v = event.get(key)
                if isinstance(v, (int, float)):
                    values.append(float(v))
                    break
        return values

    def _extract_timestamps(
        self, events: list[dict[str, Any]], window: TimeWindow | None = None
    ) -> list[datetime]:
        timestamps: list[datetime] = []
        for event in events:
            ts_str = event.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
                if window is not None and not window.contains(ts):
                    continue
                timestamps.append(ts)
            except (ValueError, TypeError):
                pass
        return timestamps

    def get_threat_trends(
        self, window: TimeWindow | None = None
    ) -> list[TrendData]:
        with self._lock:
            values = self._extract_metric_values(self._threat_events, window)
            timestamps = self._extract_timestamps(self._threat_events, window)
            if not values:
                return []
            trend = self._trend_analyzer.analyze(
                "threat_volume", values, timestamps or None
            )
            return [trend]

    def get_policy_trends(
        self, window: TimeWindow | None = None
    ) -> list[TrendData]:
        with self._lock:
            values = self._extract_metric_values(self._policy_events, window)
            timestamps = self._extract_timestamps(self._policy_events, window)
            if not values:
                return []
            trend = self._trend_analyzer.analyze(
                "policy_activity", values, timestamps or None
            )
            return [trend]

    def get_risk_trends(
        self, window: TimeWindow | None = None
    ) -> list[TrendData]:
        with self._lock:
            values = self._extract_metric_values(self._risk_events, window)
            timestamps = self._extract_timestamps(self._risk_events, window)
            if not values:
                return []
            trend = self._trend_analyzer.analyze(
                "risk_score", values, timestamps or None
            )
            return [trend]

    def get_response_trends(
        self, window: TimeWindow | None = None
    ) -> list[TrendData]:
        with self._lock:
            values = self._extract_metric_values(self._response_events, window)
            timestamps = self._extract_timestamps(self._response_events, window)
            if not values:
                return []
            trend = self._trend_analyzer.analyze(
                "response_metrics", values, timestamps or None
            )
            return [trend]

    def get_provider_accuracy(self) -> dict[str, float]:
        with self._lock:
            provider_confidences: dict[str, list[float]] = defaultdict(list)
            for event in self._provider_events:
                provider = event.get("provider", event.get("source", "unknown"))
                confidence = event.get("accuracy", event.get("confidence", event.get("value")))
                if isinstance(confidence, (int, float)):
                    provider_confidences[str(provider)].append(float(confidence))
            result: dict[str, float] = {}
            for provider, values in provider_confidences.items():
                result[provider] = self._statistics.mean(values)
            return result

    def get_plugin_usage(self) -> dict[str, int]:
        with self._lock:
            usage: dict[str, int] = Counter()
            for event in self._plugin_events:
                plugin = event.get("plugin", event.get("name", "unknown"))
                usage[str(plugin)] += 1
            return dict(usage)

    def get_quantum_usage(self) -> dict[str, int]:
        with self._lock:
            usage: dict[str, int] = Counter()
            for event in self._quantum_events:
                model = event.get("model", event.get("quantum_model", event.get("name", "unknown")))
                usage[str(model)] += 1
            return dict(usage)

    def get_fusion_strategy_usage(self) -> dict[str, int]:
        with self._lock:
            usage: dict[str, int] = Counter()
            for event in self._fusion_events:
                strategy = event.get("strategy", event.get("fusion_strategy", event.get("name", "unknown")))
                usage[str(strategy)] += 1
            return dict(usage)

    def get_average_confidence(self) -> float:
        with self._lock:
            if not self._confidence_values:
                return 0.0
            return self._statistics.mean(self._confidence_values)

    def get_top_threat_types(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            counts: dict[str, int] = Counter()
            for event in self._threat_events:
                threat_type = event.get("type", event.get("threat_type", event.get("name", "unknown")))
                counts[str(threat_type)] += 1
            sorted_threats = sorted(counts.items(), key=lambda x: x[1], reverse=True)
            return [
                {"type": t, "count": c}
                for t, c in sorted_threats[:limit]
            ]

    def get_top_policies(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            counts: dict[str, int] = Counter()
            for event in self._policy_events:
                policy = event.get("policy", event.get("policy_name", event.get("name", "unknown")))
                counts[str(policy)] += 1
            sorted_policies = sorted(counts.items(), key=lambda x: x[1], reverse=True)
            return [
                {"policy": p, "count": c}
                for p, c in sorted_policies[:limit]
            ]

    def get_most_active_sessions(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            counts: dict[str, int] = Counter()
            for event in self._session_events:
                session = event.get("session_id", event.get("session", event.get("id", "unknown")))
                counts[str(session)] += 1
            sorted_sessions = sorted(counts.items(), key=lambda x: x[1], reverse=True)
            return [
                {"session_id": s, "event_count": c}
                for s, c in sorted_sessions[:limit]
            ]

    def get_most_active_agents(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            counts: dict[str, int] = Counter()
            for event in self._agent_events:
                agent = event.get("agent_id", event.get("agent", event.get("name", "unknown")))
                counts[str(agent)] += 1
            sorted_agents = sorted(counts.items(), key=lambda x: x[1], reverse=True)
            return [
                {"agent_id": a, "event_count": c}
                for a, c in sorted_agents[:limit]
            ]

    def forecast(
        self, metric_name: str, horizon_hours: int = 24
    ) -> ForecastResult | None:
        with self._lock:
            self._ensure_initialized()
            points = self._metric_points.get(metric_name)
            if not points or len(points) < 2:
                return None
            values = [p.value for p in points]
            timestamps = [p.timestamp for p in points]
            result = self._forecast_engine.forecast(
                metric_name=metric_name,
                values=values,
                horizon=horizon_hours,
            )
            logger.debug(
                "forecast_generated",
                metric_name=metric_name,
                horizon=horizon_hours,
                method=result.method,
            )
            return result

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "initialized": self._initialized,
                "granularity": self._granularity.value,
                "total_events": len(self._events),
                "total_metric_series": len(self._metric_points),
                "threat_events": len(self._threat_events),
                "policy_events": len(self._policy_events),
                "risk_events": len(self._risk_events),
                "response_events": len(self._response_events),
                "provider_events": len(self._provider_events),
                "plugin_events": len(self._plugin_events),
                "quantum_events": len(self._quantum_events),
                "fusion_events": len(self._fusion_events),
                "session_events": len(self._session_events),
                "agent_events": len(self._agent_events),
                "confidence_values_count": len(self._confidence_values),
                "average_confidence": self.get_average_confidence(),
                "config": self._config,
            }
