"""Tests for ActionEngine, responders, Notifier, and AuditTrail."""

from q_guardian.risk.actions.action_engine import ActionEngine
from q_guardian.risk.actions.audit import AuditTrail
from q_guardian.risk.actions.notifier import Notifier
from q_guardian.risk.actions.responders import (
    AlertResponder,
    AuditLogResponder,
    BlockResponder,
    ContinueResponder,
    NotifyAdminResponder,
    WebhookResponder,
)
from q_guardian.risk.data import (
    Notification,
    PolicyDecision,
    RiskAssessment,
)
from q_guardian.risk.enums import (
    AuditStatus,
    DecisionOutcome,
    PolicyAction,
    RiskLevel,
    Severity,
)


def _make_decision(**kwargs) -> PolicyDecision:
    defaults = {
        "policy_name": "test",
        "outcome": DecisionOutcome.ALLOWED,
        "action": PolicyAction.ALLOW,
        "risk_score": 0.5,
    }
    defaults.update(kwargs)
    return PolicyDecision(**defaults)


def _make_assessment(**kwargs) -> RiskAssessment:
    defaults = {"risk_score": 0.5, "risk_level": RiskLevel.MODERATE}
    defaults.update(kwargs)
    return RiskAssessment(**defaults)


class TestResponders:
    def test_continue_responder(self):
        r = ContinueResponder()
        d = _make_decision()
        result = r.execute(d)
        assert result.success is True
        assert result.action_type == "continue"

    def test_block_responder(self):
        r = BlockResponder()
        d = _make_decision()
        result = r.execute(d)
        assert result.success is True
        assert result.action_type == "block"

    def test_audit_log_responder(self):
        r = AuditLogResponder()
        d = _make_decision()
        result = r.execute(d)
        assert result.success is True
        assert len(r.records) == 1

    def test_alert_responder(self):
        r = AlertResponder()
        d = _make_decision()
        result = r.execute(d)
        assert result.success is True
        assert len(r.notifications) == 1

    def test_notify_admin_responder(self):
        r = NotifyAdminResponder()
        d = _make_decision()
        result = r.execute(d)
        assert result.success is True
        assert len(r.notifications) == 1

    def test_webhook_responder(self):
        r = WebhookResponder()
        d = _make_decision()
        result = r.execute(d)
        assert result.success is True
        assert result.details.get("placeholder") is True

    def test_responder_health(self):
        r = ContinueResponder()
        h = r.health()
        assert h["status"] == "healthy"

    def test_action_result_has_timing(self):
        r = BlockResponder()
        d = _make_decision()
        result = r.execute(d)
        assert result.execution_time_ms >= 0

    def test_audit_log_records_decision(self):
        r = AuditLogResponder()
        d = _make_decision(decision_id="dec-123")
        result = r.execute(d)
        assert result.details["record_id"]

    def test_alert_responder_high_risk(self):
        r = AlertResponder()
        d = _make_decision(risk_score=0.9)
        result = r.execute(d)
        assert result.success


class TestNotifier:
    def test_send_notification(self):
        n = Notifier()
        notif = Notification(title="Test", message="msg", severity=Severity.LOW)
        sent = n.send(notif)
        assert sent is True
        assert n.notification_count == 1

    def test_disabled_channel(self):
        n = Notifier()
        n.disable_channel("alert")
        notif = Notification(title="Test", message="msg", channel="alert")
        sent = n.send(notif)
        assert sent is False
        assert n.notification_count == 0

    def test_enable_channel(self):
        n = Notifier()
        n.disable_channel("alert")
        n.enable_channel("alert")
        notif = Notification(title="Test", message="msg", channel="alert")
        sent = n.send(notif)
        assert sent is True

    def test_send_alert(self):
        n = Notifier()
        notif = n.send_alert("Alert!", "Something happened", Severity.HIGH)
        assert notif.sent is True
        assert n.notification_count == 1

    def test_get_notifications_filtered(self):
        n = Notifier()
        n.send(Notification(title="A", message="a", channel="alert", severity=Severity.HIGH))
        n.send(Notification(title="B", message="b", channel="default", severity=Severity.LOW))
        assert len(n.get_notifications(channel="alert")) == 1
        assert len(n.get_notifications(severity=Severity.LOW)) == 1

    def test_clear(self):
        n = Notifier()
        n.send(Notification(title="A", message="a"))
        n.clear()
        assert n.notification_count == 0


class TestAuditTrail:
    def test_record(self):
        trail = AuditTrail()
        a = _make_assessment()
        d = _make_decision()
        record = trail.record(a, d)
        assert trail.record_count == 1
        assert record.status == AuditStatus.ACTIVE

    def test_get_record(self):
        trail = AuditTrail()
        a = _make_assessment()
        d = _make_decision()
        record = trail.record(a, d)
        got = trail.get_record(record.record_id)
        assert got is not None
        assert got.record_id == record.record_id

    def test_get_record_not_found(self):
        trail = AuditTrail()
        assert trail.get_record("nonexistent") is None

    def test_update_status(self):
        trail = AuditTrail()
        a = _make_assessment()
        d = _make_decision()
        record = trail.record(a, d)
        updated = trail.update_status(record.record_id, AuditStatus.RESOLVED)
        assert updated is True
        assert trail.get_record(record.record_id).status == AuditStatus.RESOLVED

    def test_update_status_not_found(self):
        trail = AuditTrail()
        assert trail.update_status("nope", AuditStatus.RESOLVED) is False

    def test_query_outcome(self):
        trail = AuditTrail()
        trail.record(_make_assessment(), _make_decision(outcome=DecisionOutcome.BLOCKED))
        trail.record(_make_assessment(), _make_decision(outcome=DecisionOutcome.ALLOWED))
        results = trail.query(outcome=DecisionOutcome.BLOCKED)
        assert len(results) == 1

    def test_query_severity(self):
        trail = AuditTrail()
        a = _make_assessment()
        a.severity.severity = Severity.HIGH
        trail.record(a, _make_decision())
        results = trail.query(severity=Severity.HIGH)
        assert len(results) == 1

    def test_query_limit(self):
        trail = AuditTrail()
        for _ in range(10):
            trail.record(_make_assessment(), _make_decision())
        results = trail.query(limit=3)
        assert len(results) == 3

    def test_get_summary(self):
        trail = AuditTrail()
        trail.record(_make_assessment(), _make_decision(outcome=DecisionOutcome.BLOCKED))
        trail.record(_make_assessment(), _make_decision(outcome=DecisionOutcome.ALLOWED))
        summary = trail.get_summary()
        assert summary["total_records"] == 2
        assert "blocked" in summary["outcomes"]

    def test_clear(self):
        trail = AuditTrail()
        trail.record(_make_assessment(), _make_decision())
        count = trail.clear()
        assert count == 1
        assert trail.record_count == 0


class TestActionEngine:
    def test_default_responders(self):
        engine = ActionEngine()
        responders = engine.list_responders()
        assert "allow" in responders
        assert "block" in responders
        assert "warn" in responders

    def test_execute_allow(self):
        engine = ActionEngine()
        d = _make_decision(action=PolicyAction.ALLOW)
        result = engine.execute(d)
        assert result.success is True
        assert engine.execution_count == 1

    def test_execute_block(self):
        engine = ActionEngine()
        d = _make_decision(action=PolicyAction.BLOCK)
        result = engine.execute(d)
        assert result.success is True

    def test_execute_with_assessment(self):
        engine = ActionEngine()
        d = _make_decision()
        a = _make_assessment()
        result = engine.execute(d, assessment=a)
        assert result.success is True
        assert engine.audit_trail.record_count == 1

    def test_execute_batch(self):
        engine = ActionEngine()
        decisions = [_make_decision() for _ in range(5)]
        results = engine.execute_batch(decisions)
        assert len(results) == 5
        assert engine.execution_count == 5

    def test_action_history(self):
        engine = ActionEngine()
        engine.execute(_make_decision())
        engine.execute(_make_decision())
        assert len(engine.action_history) == 2

    def test_register_custom_responder(self):
        engine = ActionEngine()
        custom = ContinueResponder()
        engine.register_responder(PolicyAction.CUSTOM, custom)
        assert engine.get_responder(PolicyAction.CUSTOM) is custom

    def test_register_responder_overrides(self):
        engine = ActionEngine()
        custom = BlockResponder()
        engine.register_responder(PolicyAction.ALLOW, custom)
        assert engine.get_responder(PolicyAction.ALLOW) is custom
