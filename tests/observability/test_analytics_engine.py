import pytest

from q_guardian.observability.analytics.analytics_engine import AnalyticsEngine
from q_guardian.observability.data import AnalyticsReport
from q_guardian.observability.enums import TrendDirection
from q_guardian.observability.exceptions import AnalyticsError


class TestAnalyticsEngineInitialization:
    def test_init_default_config(self) -> None:
        engine = AnalyticsEngine()
        assert engine._initialized is False

    def test_init_with_config(self) -> None:
        engine = AnalyticsEngine(config={"granularity": "hour"})
        assert engine._config["granularity"] == "hour"

    def test_initialize(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        assert engine._initialized is True

    def test_operations_before_init_raise_error(self) -> None:
        engine = AnalyticsEngine()
        with pytest.raises(AnalyticsError):
            engine.ingest_event({"type": "test"})
        with pytest.raises(AnalyticsError):
            engine.record_metric_event("m", 1.0)


class TestAnalyticsEngineIngestion:
    def test_ingest_event_dict(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.ingest_event({"type": "threat_detected", "value": 1})
        d = engine.to_dict()
        assert d["total_events"] == 1

    def test_ingest_event_non_dict(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.ingest_event("some string event")
        d = engine.to_dict()
        assert d["total_events"] == 1

    def test_record_metric_event(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.record_metric_event("latency", 42.5)
        d = engine.to_dict()
        assert d["total_metric_series"] == 1

    def test_ingest_threat_event_categorizes(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.ingest_event({"type": "threat_detected", "value": 5})
        d = engine.to_dict()
        assert d["threat_events"] == 1

    def test_ingest_policy_event_categorizes(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.ingest_event({"type": "policy_enforced", "count": 3})
        d = engine.to_dict()
        assert d["policy_events"] == 1

    def test_ingest_risk_event_categorizes(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.ingest_event({"type": "risk_score", "value": 0.8})
        d = engine.to_dict()
        assert d["risk_events"] == 1

    def test_ingest_response_event_categorizes(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.ingest_event({"type": "response_sent", "count": 1})
        d = engine.to_dict()
        assert d["response_events"] == 1

    def test_ingest_confidence_tracks_value(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.ingest_event({"type": "detection", "confidence": 0.95})
        assert engine.get_average_confidence() == pytest.approx(0.95)


class TestAnalyticsEngineRetrieval:
    def test_get_threat_trends_empty(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        trends = engine.get_threat_trends()
        assert trends == []

    def test_get_threat_trends_with_data(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        for i in range(5):
            engine.ingest_event({"type": "threat_detected", "value": i})
        trends = engine.get_threat_trends()
        assert len(trends) == 1
        assert trends[0].direction in TrendDirection

    def test_get_policy_trends_empty(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        assert engine.get_policy_trends() == []

    def test_get_risk_trends_empty(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        assert engine.get_risk_trends() == []

    def test_get_response_trends_empty(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        assert engine.get_response_trends() == []

    def test_get_provider_accuracy(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.ingest_event({"type": "provider_accuracy", "provider": "openai", "accuracy": 0.9})
        result = engine.get_provider_accuracy()
        assert "openai" in result
        assert result["openai"] == pytest.approx(0.9)

    def test_get_plugin_usage(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.ingest_event({"type": "plugin_used", "plugin": "scanner"})
        usage = engine.get_plugin_usage()
        assert usage.get("scanner") == 1

    def test_get_quantum_usage(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.ingest_event({"type": "quantum_used", "model": "q1"})
        usage = engine.get_quantum_usage()
        assert usage.get("q1") == 1

    def test_get_fusion_strategy_usage(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.ingest_event({"type": "fusion_strategy", "strategy": "weighted"})
        usage = engine.get_fusion_strategy_usage()
        assert usage.get("weighted") == 1

    def test_get_average_confidence_empty(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        assert engine.get_average_confidence() == 0.0

    def test_get_average_confidence(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.ingest_event({"confidence": 0.8})
        engine.ingest_event({"confidence": 0.6})
        assert engine.get_average_confidence() == pytest.approx(0.7)

    def test_get_top_threat_types(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.ingest_event({"type": "threat_detected", "threat_type": "injection"})
        engine.ingest_event({"type": "threat_detected", "threat_type": "injection"})
        result = engine.get_top_threat_types()
        assert len(result) >= 1
        assert result[0]["count"] == 2

    def test_get_top_policies(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.ingest_event({"type": "policy_enforced", "policy": "block"})
        result = engine.get_top_policies()
        assert len(result) >= 1

    def test_get_most_active_sessions(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.ingest_event({"type": "session_event", "session_id": "s1"})
        result = engine.get_most_active_sessions()
        assert len(result) >= 1
        assert result[0]["session_id"] == "s1"

    def test_get_most_active_agents(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.ingest_event({"type": "agent_event", "agent_id": "a1"})
        result = engine.get_most_active_agents()
        assert len(result) >= 1
        assert result[0]["agent_id"] == "a1"


class TestAnalyticsEngineReport:
    def test_generate_report(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        report = engine.generate_report()
        assert isinstance(report, AnalyticsReport)
        assert report.title == "Q-Guardian Analytics Report"

    def test_generate_report_empty(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        report = engine.generate_report()
        assert report.threat_trends == []
        assert report.policy_trends == []
        assert report.risk_trends == []
        assert report.response_trends == []

    def test_forecast_returns_none_for_insufficient_data(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        engine.record_metric_event("m", 1.0)
        result = engine.forecast("m")
        assert result is None

    def test_forecast_with_sufficient_data(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        for i in range(5):
            engine.record_metric_event("latency", float(i))
        result = engine.forecast("latency")
        assert result is not None
        assert len(result.forecast_values) > 0

    def test_to_dict(self) -> None:
        engine = AnalyticsEngine()
        engine.initialize()
        d = engine.to_dict()
        assert "initialized" in d
        assert d["initialized"] is True
        assert "total_events" in d
        assert "granularity" in d
