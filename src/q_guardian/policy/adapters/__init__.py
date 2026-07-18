"""DSL Adapters — convert policies to/from Rego, Cedar, YAML, and JSON formats."""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from q_guardian.policy.data import (
    AdvancedPolicyDefinition,
    AdvancedRule,
    Condition,
    CompoundCondition,
    DSLAdapterResult,
)
from q_guardian.policy.enums import ComparisonOperator, DSLFormat, LogicalOperator
from q_guardian.policy.exceptions import DSLAdapterError

logger = structlog.get_logger(__name__)


class DSLAdapter:
    """Base class for DSL adapters."""

    format: DSLFormat = DSLFormat.CUSTOM

    def to_policy(self, raw: str) -> DSLAdapterResult:
        raise NotImplementedError

    def from_policy(self, policy: AdvancedPolicyDefinition) -> DSLAdapterResult:
        raise NotImplementedError


class RegoAdapter(DSLAdapter):
    """Adapter for Open Policy Agent (OPA) Rego-like policies."""

    format = DSLFormat.REGO

    def to_policy(self, raw: str) -> DSLAdapterResult:
        try:
            return self._parse_rego(raw)
        except Exception as e:
            return DSLAdapterResult(
                source_format=DSLFormat.REGO,
                raw_source=raw,
                success=False,
                errors=[str(e)],
            )

    def _parse_rego(self, raw: str) -> DSLAdapterResult:
        """Parse a simplified Rego-like format.

        Supports:
            package policy
            default allow = false
            allow {
                input.risk_score >= 0.9
                input.severity == "critical"
            }
        """
        rules: list[AdvancedRule] = []
        errors: list[str] = []
        warnings: list[str] = []

        # Extract package name
        pkg_match = re.search(r"package\s+(\w+)", raw)
        policy_name = pkg_match.group(1) if pkg_match else "rego-imported"

        # Extract default
        default_match = re.search(r"default\s+(\w+)\s*=\s*(\w+)", raw)
        default_action = default_match.group(2) if default_match else "allow"

        # Extract rule blocks
        rule_pattern = re.compile(
            r"(\w+)\s*\{([^}]+)\}", re.MULTILINE | re.DOTALL
        )
        for m in rule_pattern.finditer(raw):
            action = m.group(1)
            body = m.group(2).strip()

            # Parse conditions from body lines
            conditions = []
            for line in body.split("\n"):
                line = line.strip().rstrip(",")
                if not line or line.startswith("#"):
                    continue
                cond = self._parse_rego_condition(line)
                if cond:
                    conditions.append(cond)
                else:
                    warnings.append(f"Could not parse Rego condition: {line}")

            if conditions:
                if len(conditions) == 1:
                    condition = conditions[0]
                else:
                    condition = CompoundCondition(
                        operator=LogicalOperator.AND, conditions=conditions
                    )
                rules.append(
                    AdvancedRule(
                        name=f"rego_{action}",
                        condition=condition,
                        action=action,
                    )
                )

        policy = AdvancedPolicyDefinition(
            name=policy_name,
            description=f"Imported from Rego format",
            rules=rules,
            default_action=default_action,
        )

        return DSLAdapterResult(
            source_format=DSLFormat.REGO,
            raw_source=raw,
            policy=policy,
            errors=errors,
            warnings=warnings,
        )

    @staticmethod
    def _parse_rego_condition(line: str) -> Condition | None:
        """Parse a single Rego condition line like ``input.risk_score >= 0.9``."""
        line = line.strip().rstrip(",")
        # Remove "input." prefix
        line = re.sub(r"^input\.", "", line)

        ops = [
            (">=", ComparisonOperator.GTE),
            ("<=", ComparisonOperator.LTE),
            ("!=", ComparisonOperator.NEQ),
            ("==", ComparisonOperator.EQ),
            (">", ComparisonOperator.GT),
            ("<", ComparisonOperator.LT),
        ]
        for op_str, op_enum in ops:
            if op_str in line:
                parts = line.split(op_str, 1)
                if len(parts) == 2:
                    field = parts[0].strip()
                    raw_val = parts[1].strip().strip('"').strip("'")
                    try:
                        value = float(raw_val)
                    except ValueError:
                        value = raw_val
                    return Condition(field=field, operator=op_enum, value=value)
        return None

    def from_policy(self, policy: AdvancedPolicyDefinition) -> DSLAdapterResult:
        lines = [f"package {policy.name}", ""]
        lines.append(f"default {policy.default_action} = false")
        lines.append("")

        for rule in policy.rules:
            if not rule.enabled:
                continue
            cond_str = self._condition_to_rego(rule.condition)
            lines.append(f"{rule.action} {{")
            lines.append(f"    {cond_str}")
            lines.append("}")
            lines.append("")

        return DSLAdapterResult(
            source_format=DSLFormat.REGO,
            target_format=DSLFormat.REGO,
            raw_source="\n".join(lines),
            policy=policy,
        )

    @staticmethod
    def _condition_to_rego(cond: Any) -> str:
        if isinstance(cond, Condition):
            op_map = {
                ComparisonOperator.EQ: "==",
                ComparisonOperator.NEQ: "!=",
                ComparisonOperator.GT: ">",
                ComparisonOperator.GTE: ">=",
                ComparisonOperator.LT: "<",
                ComparisonOperator.LTE: "<=",
            }
            op = op_map.get(cond.operator, "==")
            val = f'"{cond.value}"' if isinstance(cond.value, str) else cond.value
            return f"input.{cond.field} {op} {val}"
        if isinstance(cond, CompoundCondition):
            parts = [RegoAdapter._condition_to_rego(c) for c in cond.conditions]
            joiner = f" {cond.operator.value} "
            return f"({joiner.join(parts)})"
        return "true"


class CedarAdapter(DSLAdapter):
    """Adapter for AWS Cedar-like policies."""

    format = DSLFormat.CEDAR

    def to_policy(self, raw: str) -> DSLAdapterResult:
        try:
            return self._parse_cedar(raw)
        except Exception as e:
            return DSLAdapterResult(
                source_format=DSLFormat.CEDAR,
                raw_source=raw,
                success=False,
                errors=[str(e)],
            )

    def _parse_cedar(self, raw: str) -> DSLAdapterResult:
        """Parse a simplified Cedar-like policy.

        Supports:
            permit(principal, action == "block", resource)
            when { context.risk_score >= 0.9 };
        """
        rules: list[AdvancedRule] = []
        errors: list[str] = []
        warnings: list[str] = []

        # Extract permit/deny blocks
        policy_pattern = re.compile(
            r"(permit|deny)\s*\([^)]*\)\s*(?:when\s*\{([^}]*)\})?\s*;",
            re.MULTILINE | re.DOTALL,
        )

        for m in policy_pattern.finditer(raw):
            effect = m.group(1)
            when_body = m.group(2)

            action = "allow" if effect == "permit" else "block"
            conditions = []

            if when_body:
                for line in when_body.split("\n"):
                    line = line.strip().rstrip(";").rstrip(",")
                    if not line:
                        continue
                    cond = RegoAdapter._parse_rego_condition(line)
                    if cond:
                        conditions.append(cond)
                    else:
                        warnings.append(f"Could not parse Cedar condition: {line}")

            if conditions:
                if len(conditions) == 1:
                    condition = conditions[0]
                else:
                    condition = CompoundCondition(
                        operator=LogicalOperator.AND, conditions=conditions
                    )
            else:
                condition = Condition(
                    field="__always_true__",
                    operator=ComparisonOperator.EQ,
                    value=True,
                )

            rules.append(
                AdvancedRule(
                    name=f"cedar_{effect}",
                    condition=condition,
                    action=action,
                )
            )

        policy = AdvancedPolicyDefinition(
            name="cedar-imported",
            description="Imported from Cedar format",
            rules=rules,
        )

        return DSLAdapterResult(
            source_format=DSLFormat.CEDAR,
            raw_source=raw,
            policy=policy,
            errors=errors,
            warnings=warnings,
        )

    def from_policy(self, policy: AdvancedPolicyDefinition) -> DSLAdapterResult:
        lines: list[str] = []
        for rule in policy.rules:
            if not rule.enabled:
                continue
            effect = "permit" if rule.action in ("allow", "permit") else "deny"
            cond_str = CedarAdapter._condition_to_cedar(rule.condition)
            if cond_str:
                lines.append(f'{effect}(principal, action, resource) when {{ {cond_str} }};')
            else:
                lines.append(f"{effect}(principal, action, resource);")

        return DSLAdapterResult(
            source_format=DSLFormat.CEDAR,
            target_format=DSLFormat.CEDAR,
            raw_source="\n".join(lines),
            policy=policy,
        )

    @staticmethod
    def _condition_to_cedar(cond: Any) -> str:
        if isinstance(cond, Condition):
            op_map = {
                ComparisonOperator.EQ: "==",
                ComparisonOperator.NEQ: "!=",
                ComparisonOperator.GT: ">",
                ComparisonOperator.GTE: ">=",
                ComparisonOperator.LT: "<",
                ComparisonOperator.LTE: "<=",
            }
            op = op_map.get(cond.operator, "==")
            val = f'"{cond.value}"' if isinstance(cond.value, str) else cond.value
            return f"context.{cond.field} {op} {val}"
        if isinstance(cond, CompoundCondition):
            parts = [CedarAdapter._condition_to_cedar(c) for c in cond.conditions]
            joiner = f" {cond.operator.value} "
            return f"({joiner.join(parts)})"
        return ""


class YAMLAdapter(DSLAdapter):
    """Adapter for YAML policy definitions."""

    format = DSLFormat.YAML

    def to_policy(self, raw: str) -> DSLAdapterResult:
        try:
            # Try to parse as YAML-like structure manually (no pyyaml dependency)
            data = self._simple_yaml_parse(raw)
            return self._dict_to_policy(data, raw)
        except Exception as e:
            return DSLAdapterResult(
                source_format=DSLFormat.YAML,
                raw_source=raw,
                success=False,
                errors=[str(e)],
            )

    @staticmethod
    def _simple_yaml_parse(raw: str) -> dict[str, Any]:
        """Minimal YAML-like parser for policy definitions."""
        result: dict[str, Any] = {}
        current_key = None
        for line in raw.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # Handle list item markers: "- key: value" or "- "
            is_list_item = stripped.startswith("- ")
            if is_list_item:
                stripped = stripped[2:].strip()

            if ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if val:
                    # Remove quotes
                    val = val.strip("'\"")
                    try:
                        val = float(val)
                    except ValueError:
                        if val.lower() in ("true", "false"):
                            val = val.lower() == "true"
                if key == "rules" and not is_list_item:
                    if current_key != "rules":
                        result.setdefault("rules", [])
                    current_key = "rules"
                elif current_key == "rules" and is_list_item and not val:
                    result["rules"].append({})
                elif current_key == "rules" and is_list_item and val:
                    # List item with inline value: "- name: block-high"
                    new_rule: dict[str, Any] = {key: val}
                    result["rules"].append(new_rule)
                elif current_key == "rules" and len(result["rules"]) > 0:
                    result["rules"][-1][key] = val
                else:
                    result[key] = val
        return result

    def _dict_to_policy(self, data: dict[str, Any], raw: str) -> DSLAdapterResult:
        rules: list[AdvancedRule] = []
        for rule_data in data.get("rules", []):
            if isinstance(rule_data, dict):
                condition = Condition(
                    field=rule_data.get("field", ""),
                    operator=ComparisonOperator(rule_data.get("operator", "==")),
                    value=rule_data.get("value", ""),
                )
                rules.append(
                    AdvancedRule(
                        name=rule_data.get("name", ""),
                        condition=condition,
                        action=rule_data.get("action", "allow"),
                        severity=rule_data.get("severity", "medium"),
                        priority=int(rule_data.get("priority", 0)),
                    )
                )

        policy = AdvancedPolicyDefinition(
            name=data.get("name", "yaml-imported"),
            description=data.get("description", ""),
            rules=rules,
            default_action=data.get("default_action", "allow"),
        )

        return DSLAdapterResult(
            source_format=DSLFormat.YAML,
            raw_source=raw,
            policy=policy,
        )

    def from_policy(self, policy: AdvancedPolicyDefinition) -> DSLAdapterResult:
        lines = [
            f"name: {policy.name}",
            f"description: {policy.description}",
            f"version: {policy.version}",
            f"default_action: {policy.default_action}",
            "rules:",
        ]
        for rule in policy.rules:
            if not rule.enabled:
                continue
            lines.append(f"  - name: {rule.name}")
            lines.append(f"    action: {rule.action}")
            lines.append(f"    severity: {rule.severity}")
            lines.append(f"    priority: {rule.priority}")
            if isinstance(rule.condition, Condition):
                lines.append(f"    field: {rule.condition.field}")
                lines.append(f"    operator: {rule.condition.operator.value}")
                lines.append(f"    value: {rule.condition.value}")

        return DSLAdapterResult(
            source_format=DSLFormat.YAML,
            target_format=DSLFormat.YAML,
            raw_source="\n".join(lines),
            policy=policy,
        )


class JSONAdapter(DSLAdapter):
    """Adapter for JSON policy definitions."""

    format = DSLFormat.JSON

    def to_policy(self, raw: str) -> DSLAdapterResult:
        try:
            data = json.loads(raw)
            return self._dict_to_policy(data, raw)
        except Exception as e:
            return DSLAdapterResult(
                source_format=DSLFormat.JSON,
                raw_source=raw,
                success=False,
                errors=[str(e)],
            )

    def _dict_to_policy(self, data: dict[str, Any], raw: str) -> DSLAdapterResult:
        rules: list[AdvancedRule] = []
        for rule_data in data.get("rules", []):
            condition = Condition(
                field=rule_data.get("field", ""),
                operator=ComparisonOperator(rule_data.get("operator", "==")),
                value=rule_data.get("value", ""),
            )
            rules.append(
                AdvancedRule(
                    name=rule_data.get("name", ""),
                    condition=condition,
                    action=rule_data.get("action", "allow"),
                    severity=rule_data.get("severity", "medium"),
                    priority=int(rule_data.get("priority", 0)),
                )
            )

        policy = AdvancedPolicyDefinition(
            name=data.get("name", "json-imported"),
            description=data.get("description", ""),
            rules=rules,
            default_action=data.get("default_action", "allow"),
        )

        return DSLAdapterResult(
            source_format=DSLFormat.JSON,
            raw_source=raw,
            policy=policy,
        )

    def from_policy(self, policy: AdvancedPolicyDefinition) -> DSLAdapterResult:
        data = {
            "name": policy.name,
            "description": policy.description,
            "version": policy.version,
            "default_action": policy.default_action,
            "rules": [],
        }
        for rule in policy.rules:
            rule_dict: dict[str, Any] = {
                "name": rule.name,
                "action": rule.action,
                "severity": rule.severity,
                "priority": rule.priority,
                "enabled": rule.enabled,
            }
            if isinstance(rule.condition, Condition):
                rule_dict["field"] = rule.condition.field
                rule_dict["operator"] = rule.condition.operator.value
                rule_dict["value"] = rule.condition.value
            data["rules"].append(rule_dict)

        raw = json.dumps(data, indent=2)
        return DSLAdapterResult(
            source_format=DSLFormat.JSON,
            target_format=DSLFormat.JSON,
            raw_source=raw,
            policy=policy,
        )


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

ADAPTER_MAP: dict[DSLFormat, type[DSLAdapter]] = {
    DSLFormat.REGO: RegoAdapter,
    DSLFormat.CEDAR: CedarAdapter,
    DSLFormat.YAML: YAMLAdapter,
    DSLFormat.JSON: JSONAdapter,
}


def get_adapter(fmt: DSLFormat) -> DSLAdapter:
    cls = ADAPTER_MAP.get(fmt)
    if cls is None:
        raise DSLAdapterError(f"No adapter registered for format: {fmt}")
    return cls()
