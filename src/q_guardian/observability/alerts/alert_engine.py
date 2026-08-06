"""Main alert engine for Q-Guardian Observability."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any

import structlog

from q_guardian.observability.alerts.escalation import EscalationManager
from q_guardian.observability.alerts.notifier import (
    AlertNotifier,
    LogNotifier,
)
from q_guardian.observability.alerts.routing import AlertRouter
from q_guardian.observability.data import Alert, AlertEvent, AlertRule
from q_guardian.observability.enums import AlertState
from q_guardian.observability.exceptions import AlertError
from q_guardian.utils.uuid_utils import generate_uuid

logger = structlog.get_logger(__name__)


class AlertEngine:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._lock = threading.Lock()
        self._rules: dict[str, AlertRule] = {}
        self._active_alerts: dict[str, Alert] = {}
        self._history: list[Alert] = []
        self._events: list[AlertEvent] = []
        self._notifiers: list[AlertNotifier] = []
        self._router = AlertRouter()
        self._escalation_manager = EscalationManager(
            timeout_seconds=self._config.get("escalation_timeout_seconds", 600)
        )
        self._metrics_engine: Any = None
        self._initialized = False
        self._alert_cooldowns: dict[str, datetime] = {}
        logger.info("alert_engine_created")

    def initialize(self, metrics_engine: Any = None) -> None:
        with self._lock:
            self._metrics_engine = metrics_engine
            self._notifiers.append(LogNotifier())
            self._initialized = True
            logger.info("alert_engine_initialized")

    def add_rule(self, rule: AlertRule) -> None:
        with self._lock:
            if rule.rule_id in self._rules:
                raise AlertError(
                    message=f"Rule with ID {rule.rule_id} already exists",
                    details={"rule_id": rule.rule_id},
                )
            self._rules[rule.rule_id] = rule
            self._record_event(
                alert_id="",
                old_state=None,
                new_state=AlertState.PENDING,
                message=f"Rule '{rule.name}' added",
                metadata={"rule_id": rule.rule_id, "event_type": "rule_added"},
            )
            logger.info("alert_rule_added", rule_id=rule.rule_id, rule_name=rule.name)

    def remove_rule(self, rule_id: str) -> bool:
        with self._lock:
            if rule_id not in self._rules:
                logger.warning("alert_rule_remove_not_found", rule_id=rule_id)
                return False
            removed = self._rules.pop(rule_id)
            logger.info("alert_rule_removed", rule_id=rule_id, rule_name=removed.name)
            return True

    def update_rule(self, rule: AlertRule) -> bool:
        with self._lock:
            if rule.rule_id not in self._rules:
                logger.warning("alert_rule_update_not_found", rule_id=rule.rule_id)
                return False
            self._rules[rule.rule_id] = rule
            logger.info("alert_rule_updated", rule_id=rule.rule_id, rule_name=rule.name)
            return True

    def get_rule(self, rule_id: str) -> AlertRule | None:
        with self._lock:
            return self._rules.get(rule_id)

    def list_rules(self) -> list[AlertRule]:
        with self._lock:
            return list(self._rules.values())

    def evaluate_rules(self) -> list[Alert]:
        with self._lock:
            newly_fired: list[Alert] = []
            for rule in self._rules.values():
                if not rule.enabled:
                    continue
                alert = self._evaluate_single_rule(rule)
                if alert is not None:
                    newly_fired.append(alert)
            return newly_fired

    def evaluate_rule(self, rule_id: str) -> Alert | None:
        with self._lock:
            rule = self._rules.get(rule_id)
            if rule is None:
                raise AlertError(
                    message=f"Rule {rule_id} not found",
                    details={"rule_id": rule_id},
                )
            return self._evaluate_single_rule(rule)

    def get_active_alerts(self) -> list[Alert]:
        with self._lock:
            return [
                a
                for a in self._active_alerts.values()
                if a.state not in (AlertState.RESOLVED, AlertState.SUPPRESSED)
            ]

    def get_alert(self, alert_id: str) -> Alert | None:
        with self._lock:
            if alert_id in self._active_alerts:
                return self._active_alerts[alert_id]
            for alert in self._history:
                if alert.alert_id == alert_id:
                    return alert
            return None

    def acknowledge_alert(self, alert_id: str, user: str = "system") -> bool:
        with self._lock:
            alert = self._active_alerts.get(alert_id)
            if alert is None:
                logger.warning("alert_acknowledge_not_found", alert_id=alert_id)
                return False
            old_state = alert.state
            alert.acknowledge(user=user)
            self._record_event(
                alert_id=alert_id,
                old_state=old_state,
                new_state=alert.state,
                message=f"Acknowledged by {user}",
            )
            logger.info("alert_acknowledged", alert_id=alert_id, user=user)
            return True

    def resolve_alert(self, alert_id: str) -> bool:
        with self._lock:
            alert = self._active_alerts.get(alert_id)
            if alert is None:
                logger.warning("alert_resolve_not_found", alert_id=alert_id)
                return False
            old_state = alert.state
            alert.resolve()
            self._history.append(alert)
            self._record_event(
                alert_id=alert_id,
                old_state=old_state,
                new_state=alert.state,
                message="Alert resolved",
            )
            del self._active_alerts[alert_id]
            logger.info("alert_resolved", alert_id=alert_id)
            return True

    def suppress_alert(self, alert_id: str) -> bool:
        with self._lock:
            alert = self._active_alerts.get(alert_id)
            if alert is None:
                logger.warning("alert_suppress_not_found", alert_id=alert_id)
                return False
            old_state = alert.state
            alert.suppress()
            self._record_event(
                alert_id=alert_id,
                old_state=old_state,
                new_state=alert.state,
                message="Alert suppressed",
            )
            logger.info("alert_suppressed", alert_id=alert_id)
            return True

    def get_alert_history(self) -> list[Alert]:
        with self._lock:
            return list(self._history)

    def get_alert_events(self, alert_id: str | None = None) -> list[AlertEvent]:
        with self._lock:
            if alert_id is None:
                return list(self._events)
            return [e for e in self._events if e.alert_id == alert_id]

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "initialized": self._initialized,
                "total_rules": len(self._rules),
                "active_alerts": len(self._active_alerts),
                "history_count": len(self._history),
                "total_events": len(self._events),
                "notifiers": [n.name for n in self._notifiers],
                "router": self._router.to_dict(),
                "escalation": self._escalation_manager.to_dict(),
            }

    def shutdown(self) -> None:
        with self._lock:
            self._initialized = False
            self._notifiers.clear()
            logger.info("alert_engine_shutdown")

    def _evaluate_single_rule(self, rule: AlertRule) -> Alert | None:
        cooldown = self._alert_cooldowns.get(rule.rule_id)
        if cooldown is not None:
            elapsed = (datetime.now(UTC) - cooldown).total_seconds()
            if elapsed < rule.cooldown_seconds:
                return None

        metric_value = self._get_metric_value(rule.metric_name)
        if metric_value is None:
            return None

        if not rule.evaluate(metric_value):
            return None

        alert = Alert(
            alert_id=generate_uuid(),
            rule_id=rule.rule_id,
            rule_name=rule.name,
            state=AlertState.FIRING,
            severity=rule.severity,
            alert_type=rule.alert_type,
            message=(
                f"Rule '{rule.name}' triggered: {rule.condition} {rule.threshold} "
                f"(value={metric_value})"
            ),
            labels=rule.labels.copy(),
            evaluation_value=metric_value,
        )

        self._active_alerts[alert.alert_id] = alert
        self._alert_cooldowns[rule.rule_id] = datetime.now(UTC)
        self._record_event(
            alert_id=alert.alert_id,
            old_state=None,
            new_state=alert.state,
            message=alert.message,
            metadata={"metric_value": metric_value, "rule_id": rule.rule_id},
        )

        channels = self._router.route_alert(alert)
        self._notify_notifiers(alert)
        self._escalation_manager.escalate(alert)

        logger.info(
            "alert_fired",
            alert_id=alert.alert_id,
            rule_id=rule.rule_id,
            rule_name=rule.name,
            severity=rule.severity.value,
            value=metric_value,
            channels=channels,
        )
        return alert

    def _get_metric_value(self, metric_name: str) -> float | None:
        if self._metrics_engine is None:
            return None
        try:
            metric = None
            if hasattr(self._metrics_engine, "get_metric"):
                metric = self._metrics_engine.get_metric(metric_name)
            elif hasattr(self._metrics_engine, "_metrics"):
                metric = self._metrics_engine._metrics.get(metric_name)
            if metric is None:
                return None
            if hasattr(metric, "latest_value"):
                latest: float | None = metric.latest_value()
                return latest
            if hasattr(metric, "points") and metric.points:
                last_point: float | None = metric.points[-1].value
                return last_point
            return None
        except Exception as e:
            logger.error(
                "metric_fetch_error",
                metric_name=metric_name,
                error=str(e),
            )
            return None

    def _notify_notifiers(self, alert: Alert) -> None:
        for notifier in self._notifiers:
            try:
                notifier.notify(alert)
            except Exception as e:
                logger.error(
                    "notification_failed",
                    notifier=notifier.name,
                    alert_id=alert.alert_id,
                    error=str(e),
                )

    def _record_event(
        self,
        alert_id: str,
        old_state: AlertState | None,
        new_state: AlertState,
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event = AlertEvent(
            alert_id=alert_id,
            old_state=old_state,
            new_state=new_state,
            message=message,
            metadata=metadata or {},
        )
        self._events.append(event)
