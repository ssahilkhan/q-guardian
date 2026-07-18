import pytest

from q_guardian.observability.alerts.alert_rules import AlertRuleManager
from q_guardian.observability.alerts.routing import AlertRouter
from q_guardian.observability.alerts.notifier import LogNotifier, WebhookNotifier, CallbackNotifier
from q_guardian.observability.alerts.escalation import EscalationManager, EscalationPolicy
from q_guardian.observability.data import Alert, AlertRule
from q_guardian.observability.enums import AlertSeverity, AlertState, AlertType
from q_guardian.observability.exceptions import AlertError


class TestAlertRuleManager:
    def test_create_rule(self) -> None:
        mgr = AlertRuleManager()
        rule = mgr.create_rule(
            name="high_cpu",
            metric_name="cpu",
            condition="gt",
            threshold=90.0,
        )
        assert rule.name == "high_cpu"
        assert mgr.get_rule(rule.rule_id) is not None

    def test_add_rule(self) -> None:
        mgr = AlertRuleManager()
        rule = AlertRule(
            rule_id="r1",
            name="test",
            metric_name="m",
            condition="gt",
            threshold=1.0,
        )
        mgr.add_rule(rule)
        assert mgr.get_rule("r1") is not None

    def test_remove_rule(self) -> None:
        mgr = AlertRuleManager()
        rule = AlertRule(rule_id="r1", name="test", metric_name="m", condition="gt", threshold=1.0)
        mgr.add_rule(rule)
        assert mgr.remove_rule("r1") is True
        assert mgr.get_rule("r1") is None

    def test_update_rule(self) -> None:
        mgr = AlertRuleManager()
        rule = AlertRule(rule_id="r1", name="old", metric_name="m", condition="gt", threshold=1.0)
        mgr.add_rule(rule)
        updated = AlertRule(rule_id="r1", name="new", metric_name="m", condition="lt", threshold=5.0)
        assert mgr.update_rule(updated) is True
        assert mgr.get_rule("r1").name == "new"

    def test_get_rule(self) -> None:
        mgr = AlertRuleManager()
        rule = AlertRule(rule_id="r1", name="test", metric_name="m", condition="gt", threshold=1.0)
        mgr.add_rule(rule)
        assert mgr.get_rule("r1") is not None

    def test_list_rules(self) -> None:
        mgr = AlertRuleManager()
        mgr.add_rule(AlertRule(rule_id="r1", name="a", metric_name="m", condition="gt", threshold=1.0))
        mgr.add_rule(AlertRule(rule_id="r2", name="b", metric_name="m", condition="lt", threshold=5.0))
        rules = mgr.list_rules()
        assert len(rules) == 2

    def test_validate_rule_valid(self) -> None:
        mgr = AlertRuleManager()
        rule = AlertRule(name="test", metric_name="m", condition="gt", threshold=1.0)
        errors = mgr.validate_rule(rule)
        assert errors == []

    def test_validate_rule_invalid_condition(self) -> None:
        mgr = AlertRuleManager()
        rule = AlertRule(name="test", metric_name="m", condition="invalid", threshold=1.0)
        errors = mgr.validate_rule(rule)
        assert len(errors) > 0

    def test_validate_rule_no_name(self) -> None:
        mgr = AlertRuleManager()
        rule = AlertRule(name="", metric_name="m", condition="gt", threshold=1.0)
        errors = mgr.validate_rule(rule)
        assert any("name" in e.lower() for e in errors)


class TestAlertRouter:
    def test_add_route(self) -> None:
        router = AlertRouter()
        router.add_route(AlertSeverity.HIGH, "slack")
        assert "slack" in router.get_routes(AlertSeverity.HIGH)

    def test_remove_route(self) -> None:
        router = AlertRouter()
        router.add_route(AlertSeverity.HIGH, "slack")
        assert router.remove_route(AlertSeverity.HIGH, "slack") is True
        assert router.get_routes(AlertSeverity.HIGH) == []

    def test_get_routes(self) -> None:
        router = AlertRouter()
        router.add_route(AlertSeverity.CRITICAL, "pager")
        router.add_route(AlertSeverity.CRITICAL, "slack")
        routes = router.get_routes(AlertSeverity.CRITICAL)
        assert len(routes) == 2

    def test_route_alert(self) -> None:
        router = AlertRouter()
        router.add_route(AlertSeverity.HIGH, "slack")
        alert = Alert(
            alert_id="a1",
            rule_id="r1",
            state=AlertState.FIRING,
            severity=AlertSeverity.HIGH,
        )
        channels = router.route_alert(alert)
        assert "slack" in channels

    def test_default_channels(self) -> None:
        router = AlertRouter()
        router.set_default_channels(["log", "email"])
        alert = Alert(
            alert_id="a1",
            rule_id="r1",
            state=AlertState.FIRING,
            severity=AlertSeverity.MEDIUM,
        )
        channels = router.route_alert(alert)
        assert "log" in channels
        assert "email" in channels


class TestNotifiers:
    def test_log_notifier_notify_returns_true(self) -> None:
        notifier = LogNotifier()
        alert = Alert(
            alert_id="a1",
            rule_id="r1",
            state=AlertState.FIRING,
            severity=AlertSeverity.HIGH,
        )
        assert notifier.notify(alert) is True
        assert notifier.name == "log"

    def test_webhook_notifier_notify_returns_true(self) -> None:
        notifier = WebhookNotifier(url="https://example.com")
        alert = Alert(
            alert_id="a1",
            rule_id="r1",
            state=AlertState.FIRING,
            severity=AlertSeverity.HIGH,
        )
        assert notifier.notify(alert) is True
        assert len(notifier.payloads) == 1

    def test_callback_notifier_with_custom_callback(self) -> None:
        callback_called = []

        def my_callback(alert: Alert) -> bool:
            callback_called.append(alert.alert_id)
            return True

        notifier = CallbackNotifier(callback=my_callback)
        alert = Alert(
            alert_id="a1",
            rule_id="r1",
            state=AlertState.FIRING,
            severity=AlertSeverity.HIGH,
        )
        assert notifier.notify(alert) is True
        assert "a1" in callback_called


class TestEscalationManager:
    def test_add_policy(self) -> None:
        mgr = EscalationManager()
        policy = EscalationPolicy(
            name="critical_policy",
            severity=AlertSeverity.CRITICAL,
            escalation_steps=[{"delay_seconds": 0, "channels": ["log"]}],
        )
        mgr.add_policy(policy)
        assert mgr.get_policy(policy.policy_id) is not None

    def test_remove_policy(self) -> None:
        mgr = EscalationManager()
        policy = EscalationPolicy(
            name="critical_policy",
            severity=AlertSeverity.CRITICAL,
        )
        mgr.add_policy(policy)
        assert mgr.remove_policy(policy.policy_id) is True
        assert mgr.get_policy(policy.policy_id) is None

    def test_get_policy(self) -> None:
        mgr = EscalationManager()
        policy = EscalationPolicy(
            name="test_policy",
            severity=AlertSeverity.HIGH,
        )
        mgr.add_policy(policy)
        assert mgr.get_policy(policy.policy_id) is not None

    def test_should_escalate_resolved_alert(self) -> None:
        mgr = EscalationManager(timeout_seconds=0)
        alert = Alert(
            alert_id="a1",
            rule_id="r1",
            state=AlertState.RESOLVED,
            severity=AlertSeverity.HIGH,
        )
        assert mgr.should_escalate(alert) is False

    def test_should_escalate_info_severity(self) -> None:
        mgr = EscalationManager(timeout_seconds=0)
        alert = Alert(
            alert_id="a1",
            rule_id="r1",
            state=AlertState.FIRING,
            severity=AlertSeverity.INFO,
        )
        assert mgr.should_escalate(alert) is False

    def test_create_default_policy(self) -> None:
        mgr = EscalationManager()
        policy = mgr.create_default_policy(AlertSeverity.CRITICAL)
        assert policy.severity == AlertSeverity.CRITICAL
        assert len(policy.escalation_steps) > 0

    def test_create_default_policy_low(self) -> None:
        mgr = EscalationManager()
        policy = mgr.create_default_policy(AlertSeverity.LOW)
        assert policy.severity == AlertSeverity.LOW


class TestEscalationPolicy:
    def test_policy_creation(self) -> None:
        policy = EscalationPolicy(
            name="test",
            severity=AlertSeverity.HIGH,
            escalation_steps=[{"delay_seconds": 0, "channels": ["log"]}],
        )
        assert policy.name == "test"
        assert policy.severity == AlertSeverity.HIGH
        assert len(policy.escalation_steps) == 1
        assert policy.enabled is True
