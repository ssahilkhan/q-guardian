"""Tests for DSL Adapters (Rego, Cedar, YAML, JSON)."""

import json
import pytest

from q_guardian.policy.adapters import (
    RegoAdapter,
    CedarAdapter,
    YAMLAdapter,
    JSONAdapter,
    get_adapter,
)
from q_guardian.policy.data import AdvancedPolicyDefinition, AdvancedRule, Condition
from q_guardian.policy.enums import ComparisonOperator, DSLFormat
from q_guardian.policy.exceptions import DSLAdapterError


class TestRegoAdapter:
    def test_parse_simple_rego(self):
        rego = """package security

default allow = false

allow {
    input.risk_score >= 0.9
    input.severity == "critical"
}
"""
        adapter = RegoAdapter()
        result = adapter.to_policy(rego)
        assert result.success is True
        assert result.policy is not None
        assert result.policy.name == "security"
        assert len(result.policy.rules) >= 1

    def test_parse_rego_single_rule(self):
        rego = """package test
default block = false
block {
    input.score > 0.8
}
"""
        adapter = RegoAdapter()
        result = adapter.to_policy(rego)
        assert result.policy is not None
        assert result.policy.rules[0].action == "block"

    def test_export_rego(self):
        policy = AdvancedPolicyDefinition(
            name="exported",
            rules=[
                AdvancedRule(
                    name="block-high",
                    condition=Condition(
                        field="score", operator=ComparisonOperator.GTE, value=0.9
                    ),
                    action="block",
                )
            ],
            default_action="allow",
        )
        adapter = RegoAdapter()
        result = adapter.from_policy(policy)
        assert "package exported" in result.raw_source
        assert "block {" in result.raw_source

    def test_rego_with_warnings(self):
        rego = """package test
default allow = false
allow {
    unknown_syntax
}
"""
        adapter = RegoAdapter()
        result = adapter.to_policy(rego)
        assert len(result.warnings) > 0


class TestCedarAdapter:
    def test_parse_cedar_permit(self):
        cedar = """permit(principal, action, resource) when { context.score >= 0.9 };
"""
        adapter = CedarAdapter()
        result = adapter.to_policy(cedar)
        assert result.success is True
        assert result.policy is not None
        assert len(result.policy.rules) >= 1

    def test_parse_cedar_deny(self):
        cedar = """deny(principal, action, resource) when { context.level == "critical" };
"""
        adapter = CedarAdapter()
        result = adapter.to_policy(cedar)
        assert result.policy.rules[0].action == "block"

    def test_export_cedar(self):
        policy = AdvancedPolicyDefinition(
            name="cedar-export",
            rules=[
                AdvancedRule(
                    condition=Condition(
                        field="risk", operator=ComparisonOperator.GT, value=0.5
                    ),
                    action="allow",
                )
            ],
        )
        adapter = CedarAdapter()
        result = adapter.from_policy(policy)
        assert "permit" in result.raw_source

    def test_cedar_with_no_when(self):
        cedar = """permit(principal, action, resource);
"""
        adapter = CedarAdapter()
        result = adapter.to_policy(cedar)
        assert result.policy is not None


class TestYAMLAdapter:
    def test_parse_yaml(self):
        yaml = """name: yaml-test
description: A YAML policy
version: 1.0.0
default_action: allow
rules:
  - name: block-high
    action: block
    severity: high
    priority: 1
    field: risk_score
    operator: ">="
    value: "0.9"
"""
        adapter = YAMLAdapter()
        result = adapter.to_policy(yaml)
        assert result.success is True
        assert result.policy.name == "yaml-test"
        assert len(result.policy.rules) == 1

    def test_export_yaml(self):
        policy = AdvancedPolicyDefinition(
            name="yaml-export",
            rules=[
                AdvancedRule(
                    name="test-rule",
                    condition=Condition(
                        field="score", operator=ComparisonOperator.GT, value=0.5
                    ),
                    action="block",
                )
            ],
        )
        adapter = YAMLAdapter()
        result = adapter.from_policy(policy)
        assert "name: yaml-export" in result.raw_source
        assert "rules:" in result.raw_source


class TestJSONAdapter:
    def test_parse_json(self):
        data = {
            "name": "json-test",
            "description": "A JSON policy",
            "default_action": "allow",
            "rules": [
                {
                    "name": "block-high",
                    "action": "block",
                    "severity": "high",
                    "priority": 1,
                    "field": "risk_score",
                    "operator": ">=",
                    "value": 0.9,
                }
            ],
        }
        adapter = JSONAdapter()
        result = adapter.to_policy(json.dumps(data))
        assert result.success is True
        assert result.policy.name == "json-test"
        assert len(result.policy.rules) == 1

    def test_parse_invalid_json(self):
        adapter = JSONAdapter()
        result = adapter.to_policy("not json")
        assert result.success is False
        assert len(result.errors) > 0

    def test_export_json(self):
        policy = AdvancedPolicyDefinition(
            name="json-export",
            rules=[
                AdvancedRule(
                    name="test",
                    condition=Condition(
                        field="score", operator=ComparisonOperator.GT, value=0.5
                    ),
                    action="block",
                )
            ],
        )
        adapter = JSONAdapter()
        result = adapter.from_policy(policy)
        parsed = json.loads(result.raw_source)
        assert parsed["name"] == "json-export"


class TestAdapterRegistry:
    def test_get_json_adapter(self):
        adapter = get_adapter(DSLFormat.JSON)
        assert isinstance(adapter, JSONAdapter)

    def test_get_yaml_adapter(self):
        adapter = get_adapter(DSLFormat.YAML)
        assert isinstance(adapter, YAMLAdapter)

    def test_get_rego_adapter(self):
        adapter = get_adapter(DSLFormat.REGO)
        assert isinstance(adapter, RegoAdapter)

    def test_get_cedar_adapter(self):
        adapter = get_adapter(DSLFormat.CEDAR)
        assert isinstance(adapter, CedarAdapter)

    def test_unknown_format_raises(self):
        with pytest.raises(DSLAdapterError):
            get_adapter(DSLFormat.CUSTOM)
