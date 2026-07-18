"""Alert rule management for Q-Guardian Observability."""

from __future__ import annotations

import structlog
from typing import Any

from q_guardian.observability.data import AlertRule
from q_guardian.observability.enums import AlertSeverity, AlertType
from q_guardian.observability.exceptions import AlertError
from q_guardian.utils.uuid_utils import generate_uuid

logger = structlog.get_logger(__name__)

VALID_CONDITIONS = {"gt", "lt", "eq", "gte", "lte"}


class AlertRuleManager:
    def __init__(self) -> None:
        self._rules: dict[str, AlertRule] = {}
        logger.info("alert_rule_manager_initialized")

    def create_rule(
        self,
        name: str,
        metric_name: str,
        condition: str,
        threshold: float,
        severity: AlertSeverity = AlertSeverity.MEDIUM,
        alert_type: AlertType = AlertType.THRESHOLD,
        description: str = "",
        labels: dict[str, str] | None = None,
        cooldown_seconds: int = 300,
    ) -> AlertRule:
        rule = AlertRule(
            rule_id=generate_uuid(),
            name=name,
            metric_name=metric_name,
            condition=condition,
            threshold=threshold,
            severity=severity,
            alert_type=alert_type,
            description=description,
            labels=labels or {},
            cooldown_seconds=cooldown_seconds,
        )
        errors = self.validate_rule(rule)
        if errors:
            raise AlertError(
                message=f"Invalid rule: {'; '.join(errors)}",
                details={"rule_name": name, "errors": errors},
            )
        self.add_rule(rule)
        return rule

    def add_rule(self, rule: AlertRule) -> None:
        errors = self.validate_rule(rule)
        if errors:
            raise AlertError(
                message=f"Invalid rule: {'; '.join(errors)}",
                details={"rule_id": rule.rule_id, "errors": errors},
            )
        self._rules[rule.rule_id] = rule
        logger.info("alert_rule_added", rule_id=rule.rule_id, rule_name=rule.name)

    def remove_rule(self, rule_id: str) -> bool:
        if rule_id in self._rules:
            removed = self._rules.pop(rule_id)
            logger.info("alert_rule_removed", rule_id=rule_id, rule_name=removed.name)
            return True
        logger.warning("alert_rule_remove_not_found", rule_id=rule_id)
        return False

    def update_rule(self, rule: AlertRule) -> bool:
        if rule.rule_id not in self._rules:
            logger.warning("alert_rule_update_not_found", rule_id=rule.rule_id)
            return False
        errors = self.validate_rule(rule)
        if errors:
            raise AlertError(
                message=f"Invalid rule: {'; '.join(errors)}",
                details={"rule_id": rule.rule_id, "errors": errors},
            )
        self._rules[rule.rule_id] = rule
        logger.info("alert_rule_updated", rule_id=rule.rule_id, rule_name=rule.name)
        return True

    def get_rule(self, rule_id: str) -> AlertRule | None:
        return self._rules.get(rule_id)

    def list_rules(self, enabled_only: bool = False) -> list[AlertRule]:
        rules = list(self._rules.values())
        if enabled_only:
            rules = [r for r in rules if r.enabled]
        return rules

    def validate_rule(self, rule: AlertRule) -> list[str]:
        errors: list[str] = []
        if not rule.name:
            errors.append("Rule name is required")
        if not rule.metric_name:
            errors.append("Metric name is required")
        if rule.condition not in VALID_CONDITIONS:
            errors.append(
                f"Invalid condition '{rule.condition}': must be one of {sorted(VALID_CONDITIONS)}"
            )
        if rule.cooldown_seconds < 0:
            errors.append("Cooldown seconds must be non-negative")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rules": len(self._rules),
            "enabled_rules": len([r for r in self._rules.values() if r.enabled]),
            "rules": [rule.model_dump(mode="json") for rule in self._rules.values()],
        }
