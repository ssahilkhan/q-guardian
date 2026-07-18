import pytest

from q_guardian.observability.alerts.alert_engine import AlertEngine
from q_guardian.observability.data import Alert, AlertRule
from q_guardian.observability.enums import AlertSeverity, AlertState, AlertType
from q_guardian.observability.exceptions import AlertError


class TestAlertEngineInitialization:
    def test_init_default(self) -> None:
        engine = AlertEngine()
        d = engine.to_dict()
        assert d["initialized"] is False
        assert d["total_rules"] == 0

    def test_init_with_config(self) -> None:
        engine = AlertEngine(config={"escalation_timeout_seconds": 120})
        assert engine._config["escalation_timeout_seconds"] == 120

    def test_initialize(self) -> None:
        engine = AlertEngine()
        engine.initialize()
        d = engine.to_dict()
        assert d["initialized"] is True
        assert "log" in d["notifiers"]


class TestAlertEngineRules:
    def test_add_rule(self) -> None:
        engine = AlertEngine()
        rule = AlertRule(
            name="high_latency",
            metric_name="latency",
            condition="gt",
            threshold=100.0,
            alert_type=AlertType.LATENCY,
        )
        engine.add_rule(rule)
        assert engine.get_rule(rule.rule_id) is not None

    def test_add_duplicate_rule_raises(self) -> None:
        engine = AlertEngine()
        rule = AlertRule(
            rule_id="r1",
            name="test",
            metric_name="m",
            condition="gt",
            threshold=1.0,
        )
        engine.add_rule(rule)
        with pytest.raises(AlertError):
            engine.add_rule(rule)

    def test_remove_rule(self) -> None:
        engine = AlertEngine()
        rule = AlertRule(rule_id="r1", name="test", metric_name="m", condition="gt", threshold=1.0)
        engine.add_rule(rule)
        assert engine.remove_rule("r1") is True
        assert engine.get_rule("r1") is None

    def test_remove_non_existent_rule_returns_false(self) -> None:
        engine = AlertEngine()
        assert engine.remove_rule("nonexistent") is False

    def test_update_rule(self) -> None:
        engine = AlertEngine()
        rule = AlertRule(rule_id="r1", name="test", metric_name="m", condition="gt", threshold=1.0)
        engine.add_rule(rule)
        updated = AlertRule(rule_id="r1", name="updated", metric_name="m", condition="lt", threshold=5.0)
        assert engine.update_rule(updated) is True
        assert engine.get_rule("r1").name == "updated"

    def test_get_rule(self) -> None:
        engine = AlertEngine()
        rule = AlertRule(rule_id="r1", name="test", metric_name="m", condition="gt", threshold=1.0)
        engine.add_rule(rule)
        assert engine.get_rule("r1") is not None

    def test_list_rules(self) -> None:
        engine = AlertEngine()
        engine.add_rule(AlertRule(rule_id="r1", name="a", metric_name="m", condition="gt", threshold=1.0))
        engine.add_rule(AlertRule(rule_id="r2", name="b", metric_name="m", condition="lt", threshold=5.0))
        rules = engine.list_rules()
        assert len(rules) == 2


class TestAlertEngineEvaluation:
    def test_evaluate_rule_without_metrics_returns_none(self) -> None:
        engine = AlertEngine()
        engine.initialize()
        rule = AlertRule(rule_id="r1", name="test", metric_name="m", condition="gt", threshold=1.0)
        engine.add_rule(rule)
        result = engine.evaluate_rule("r1")
        assert result is None

    def test_evaluate_rules_empty_returns_empty(self) -> None:
        engine = AlertEngine()
        engine.initialize()
        results = engine.evaluate_rules()
        assert results == []

    def test_evaluate_rule_nonexistent_raises(self) -> None:
        engine = AlertEngine()
        engine.initialize()
        with pytest.raises(AlertError):
            engine.evaluate_rule("nonexistent")


class TestAlertEngineAlertManagement:
    def _create_alert_in_engine(self, engine: AlertEngine) -> str:
        rule = AlertRule(rule_id="r1", name="test", metric_name="m", condition="gt", threshold=1.0)
        engine.add_rule(rule)
        alert = Alert(
            alert_id="a1",
            rule_id="r1",
            rule_name="test",
            state=AlertState.FIRING,
            severity=AlertSeverity.HIGH,
        )
        engine._active_alerts["a1"] = alert
        return "a1"

    def test_get_active_alerts(self) -> None:
        engine = AlertEngine()
        self._create_alert_in_engine(engine)
        active = engine.get_active_alerts()
        assert len(active) == 1

    def test_get_alert(self) -> None:
        engine = AlertEngine()
        self._create_alert_in_engine(engine)
        alert = engine.get_alert("a1")
        assert alert is not None
        assert alert.alert_id == "a1"

    def test_acknowledge_alert(self) -> None:
        engine = AlertEngine()
        self._create_alert_in_engine(engine)
        assert engine.acknowledge_alert("a1", user="admin") is True
        alert = engine.get_alert("a1")
        assert alert.state == AlertState.ACKNOWLEDGED

    def test_resolve_alert(self) -> None:
        engine = AlertEngine()
        self._create_alert_in_engine(engine)
        assert engine.resolve_alert("a1") is True
        assert engine.get_active_alerts() == []

    def test_suppress_alert(self) -> None:
        engine = AlertEngine()
        self._create_alert_in_engine(engine)
        assert engine.suppress_alert("a1") is True
        alert = engine.get_alert("a1")
        assert alert.state == AlertState.SUPPRESSED

    def test_acknowledge_non_existent_returns_false(self) -> None:
        engine = AlertEngine()
        assert engine.acknowledge_alert("nonexistent") is False

    def test_resolve_non_existent_returns_false(self) -> None:
        engine = AlertEngine()
        assert engine.resolve_alert("nonexistent") is False

    def test_suppress_non_existent_returns_false(self) -> None:
        engine = AlertEngine()
        assert engine.suppress_alert("nonexistent") is False


class TestAlertEngineHistoryAndEvents:
    def test_get_alert_history(self) -> None:
        engine = AlertEngine()
        alert = Alert(
            alert_id="a1",
            rule_id="r1",
            state=AlertState.RESOLVED,
        )
        engine._history.append(alert)
        history = engine.get_alert_history()
        assert len(history) == 1

    def test_get_alert_events_all(self) -> None:
        engine = AlertEngine()
        engine._record_event("a1", None, AlertState.FIRING, "fired")
        events = engine.get_alert_events()
        assert len(events) == 1

    def test_get_alert_events_filtered(self) -> None:
        engine = AlertEngine()
        engine._record_event("a1", None, AlertState.FIRING, "fired")
        engine._record_event("a2", None, AlertState.FIRING, "fired")
        events = engine.get_alert_events("a1")
        assert len(events) == 1
        assert events[0].alert_id == "a1"


class TestAlertEngineMisc:
    def test_to_dict(self) -> None:
        engine = AlertEngine()
        d = engine.to_dict()
        assert "initialized" in d
        assert "total_rules" in d
        assert "active_alerts" in d
        assert "router" in d
        assert "escalation" in d

    def test_shutdown(self) -> None:
        engine = AlertEngine()
        engine.initialize()
        engine.shutdown()
        assert engine._initialized is False
        assert len(engine._notifiers) == 0
