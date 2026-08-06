"""Tests for the advanced condition parser."""

import pytest

from q_guardian.policy.core.condition_parser import parse_condition
from q_guardian.policy.data import CompoundCondition, Condition
from q_guardian.policy.enums import ComparisonOperator, ConditionType, LogicalOperator
from q_guardian.policy.exceptions import ConditionParseError


class TestSimpleConditions:
    def test_eq_numeric(self):
        c = parse_condition("risk_score == 0.9")
        assert isinstance(c, Condition)
        assert c.field == "risk_score"
        assert c.operator == ComparisonOperator.EQ
        assert c.value == 0.9

    def test_neq(self):
        c = parse_condition("level != low")
        assert c.operator == ComparisonOperator.NEQ
        assert c.value == "low"

    def test_gt(self):
        c = parse_condition("score > 0.5")
        assert c.operator == ComparisonOperator.GT
        assert c.value == 0.5

    def test_gte(self):
        c = parse_condition("score >= 0.8")
        assert c.operator == ComparisonOperator.GTE

    def test_lt(self):
        c = parse_condition("score < 0.3")
        assert c.operator == ComparisonOperator.LT

    def test_lte(self):
        c = parse_condition("score <= 0.1")
        assert c.operator == ComparisonOperator.LTE

    def test_matches(self):
        c = parse_condition("name =~ 'test_.*'")
        assert c.operator == ComparisonOperator.MATCHES
        assert c.value == "test_.*"

    def test_not_matches(self):
        c = parse_condition("name !~ 'admin_.*'")
        assert c.operator == ComparisonOperator.NOT_MATCHES

    def test_in_list(self):
        c = parse_condition("level in [critical, high, medium]")
        assert c.operator == ComparisonOperator.IN
        assert c.value == ["critical", "high", "medium"]

    def test_not_in_list(self):
        c = parse_condition("level not_in [low, info]")
        assert c.operator == ComparisonOperator.NOT_IN

    def test_contains(self):
        c = parse_condition("msg contains 'error'")
        assert c.operator == ComparisonOperator.CONTAINS
        assert c.value == "error"

    def test_starts_with(self):
        c = parse_condition("path starts_with '/api'")
        assert c.operator == ComparisonOperator.STARTS_WITH

    def test_ends_with(self):
        c = parse_condition("path ends_with '.py'")
        assert c.operator == ComparisonOperator.ENDS_WITH

    def test_string_value_quoted(self):
        c = parse_condition("level == 'critical'")
        assert c.value == "critical"

    def test_string_value_double_quoted(self):
        c = parse_condition('level == "critical"')
        assert c.value == "critical"


class TestCompoundConditions:
    def test_and(self):
        c = parse_condition("risk_score >= 0.8 AND confidence < 0.5")
        assert isinstance(c, CompoundCondition)
        assert c.operator == LogicalOperator.AND
        assert len(c.conditions) == 2

    def test_or(self):
        c = parse_condition("risk_level == critical OR risk_level == severe")
        assert c.operator == LogicalOperator.OR
        assert len(c.conditions) == 2

    def test_not(self):
        c = parse_condition("NOT risk_level == low")
        assert c.operator == LogicalOperator.NOT

    def test_nested_and_or(self):
        c = parse_condition("(risk_score >= 0.8 OR risk_score >= 0.9) AND confidence > 0.5")
        assert isinstance(c, CompoundCondition)
        assert c.operator == LogicalOperator.AND
        assert isinstance(c.conditions[0], CompoundCondition)
        assert c.conditions[0].operator == LogicalOperator.OR

    def test_complex_nesting(self):
        c = parse_condition(
            "(risk_level == critical OR risk_level == severe) "
            "AND (confidence > 0.7 OR threat_score >= 0.9)"
        )
        assert c.operator == LogicalOperator.AND
        assert len(c.conditions) == 2
        assert all(isinstance(cc, CompoundCondition) for cc in c.conditions)


class TestEvaluation:
    def test_simple_eq(self):
        c = parse_condition("risk_score == 0.9")
        assert c.evaluate({"risk_score": 0.9}) is True
        assert c.evaluate({"risk_score": 0.8}) is False

    def test_and_evaluation(self):
        c = parse_condition("risk_score >= 0.8 AND confidence < 0.5")
        assert c.evaluate({"risk_score": 0.9, "confidence": 0.3}) is True
        assert c.evaluate({"risk_score": 0.9, "confidence": 0.7}) is False

    def test_or_evaluation(self):
        c = parse_condition("risk_level == critical OR risk_level == severe")
        assert c.evaluate({"risk_level": "critical"}) is True
        assert c.evaluate({"risk_level": "severe"}) is True
        assert c.evaluate({"risk_level": "low"}) is False

    def test_not_evaluation(self):
        c = parse_condition("NOT risk_level == low")
        assert c.evaluate({"risk_level": "high"}) is True
        assert c.evaluate({"risk_level": "low"}) is False

    def test_in_evaluation(self):
        c = parse_condition("risk_level in [critical, severe]")
        assert c.evaluate({"risk_level": "critical"}) is True
        assert c.evaluate({"risk_level": "low"}) is False

    def test_regex_evaluation(self):
        c = parse_condition("source =~ 'web_.*'")
        assert c.evaluate({"source": "web_api"}) is True
        assert c.evaluate({"source": "db_query"}) is False

    def test_contains_evaluation(self):
        c = parse_condition("msg contains 'timeout'")
        assert c.evaluate({"msg": "connection timeout error"}) is True
        assert c.evaluate({"msg": "all good"}) is False

    def test_starts_with_evaluation(self):
        c = parse_condition("path starts_with '/api'")
        assert c.evaluate({"path": "/api/v1/users"}) is True
        assert c.evaluate({"path": "/web/index"}) is False

    def test_ends_with_evaluation(self):
        c = parse_condition("file ends_with '.exe'")
        assert c.evaluate({"file": "malware.exe"}) is True
        assert c.evaluate({"file": "data.csv"}) is False

    def test_nested_evaluation(self):
        c = parse_condition("(risk_score >= 0.8 OR risk_level == critical) AND confidence > 0.5")
        assert c.evaluate({"risk_score": 0.9, "risk_level": "low", "confidence": 0.7}) is True
        assert c.evaluate({"risk_score": 0.3, "risk_level": "critical", "confidence": 0.8}) is True
        assert c.evaluate({"risk_score": 0.3, "risk_level": "low", "confidence": 0.3}) is False


class TestTemporalConditions:
    def test_after(self):
        c = parse_condition("created after '2025-01-01'")
        assert c.operator == ComparisonOperator.GTE
        assert c.condition_type == ConditionType.TEMPORAL

    def test_before(self):
        c = parse_condition("expires before '2025-12-31'")
        assert c.operator == ComparisonOperator.LTE
        assert c.condition_type == ConditionType.TEMPORAL


class TestExistence:
    def test_exists(self):
        c = parse_condition("model_name exists")
        assert c.condition_type == ConditionType.EXISTS
        assert c.field == "model_name"


class TestEdgeCases:
    def test_empty_expression_raises(self):
        with pytest.raises(ConditionParseError):
            parse_condition("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ConditionParseError):
            parse_condition("   ")

    def test_invalid_token_raises(self):
        with pytest.raises(ConditionParseError):
            parse_condition("risk_score @ 0.9")

    def test_unmatched_paren_raises(self):
        with pytest.raises(ConditionParseError):
            parse_condition("(risk_score >= 0.8 AND confidence > 0.5")

    def test_extra_token_raises(self):
        with pytest.raises(ConditionParseError):
            parse_condition("risk_score >= 0.9 extra_token")

    def test_multiple_and_chained(self):
        c = parse_condition("a > 1 AND b > 2 AND c > 3")
        assert c.operator == LogicalOperator.AND
        assert len(c.conditions) == 3

    def test_multiple_or_chained(self):
        c = parse_condition("a == 1 OR b == 2 OR c == 3")
        assert c.operator == LogicalOperator.OR
        assert len(c.conditions) == 3
