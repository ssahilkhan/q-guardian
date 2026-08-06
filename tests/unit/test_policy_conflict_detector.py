"""Tests for the Conflict Detector."""

from q_guardian.policy.core.conflict_detector import ConflictDetector
from q_guardian.policy.data import AdvancedPolicyDefinition, AdvancedRule, Condition
from q_guardian.policy.enums import ComparisonOperator, ConflictResolution, ConflictType


def _rule(
    name: str, field: str, op: ComparisonOperator, value, action: str, priority: int = 0
) -> AdvancedRule:
    return AdvancedRule(
        name=name,
        condition=Condition(field=field, operator=op, value=value),
        action=action,
        priority=priority,
    )


def _policy(name: str, rules: list[AdvancedRule]) -> AdvancedPolicyDefinition:
    return AdvancedPolicyDefinition(name=name, rules=rules)


class TestConflictDetector:
    def test_no_conflict_different_fields(self):
        detector = ConflictDetector()
        r1 = _rule("r1", "score", ComparisonOperator.GT, 0.5, "block")
        r2 = _rule("r2", "confidence", ComparisonOperator.GT, 0.5, "warn")
        conflicts = detector.detect_rule_conflicts([r1], [r2])
        assert len(conflicts) == 0

    def test_redundant_rules(self):
        detector = ConflictDetector()
        r1 = _rule("r1", "score", ComparisonOperator.GT, 0.5, "block")
        r2 = _rule("r2", "score", ComparisonOperator.GT, 0.5, "block")
        conflicts = detector.detect_rule_conflicts([r1], [r2])
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.REDUNDANT

    def test_contradicting_rules(self):
        detector = ConflictDetector()
        r1 = _rule("r1", "score", ComparisonOperator.GT, 0.5, "block")
        r2 = _rule("r2", "score", ComparisonOperator.GT, 0.5, "allow")
        conflicts = detector.detect_rule_conflicts([r1], [r2])
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.CONTRADICTING

    def test_shadowed_rule(self):
        detector = ConflictDetector()
        r1 = _rule("r1", "score", ComparisonOperator.GT, 0.3, "block", priority=1)
        r2 = _rule("r2", "score", ComparisonOperator.GT, 0.5, "warn", priority=5)
        conflicts = detector.detect_rule_conflicts([r1], [r2])
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.SHADOWED

    def test_disabled_rules_ignored(self):
        detector = ConflictDetector()
        r1 = _rule("r1", "score", ComparisonOperator.GT, 0.5, "block")
        r1.enabled = False
        r2 = _rule("r2", "score", ComparisonOperator.GT, 0.5, "allow")
        conflicts = detector.detect_rule_conflicts([r1], [r2])
        assert len(conflicts) == 0

    def test_policy_conflicts(self):
        detector = ConflictDetector()
        p1 = _policy("p1", [_rule("r1", "score", ComparisonOperator.GT, 0.5, "block")])
        p2 = _policy("p2", [_rule("r2", "score", ComparisonOperator.GT, 0.5, "allow")])
        conflicts = detector.detect_policy_conflicts(p1, p2)
        assert len(conflicts) == 1
        assert conflicts[0].policy_id_a == p1.policy_id
        assert conflicts[0].policy_id_b == p2.policy_id

    def test_internal_conflicts(self):
        detector = ConflictDetector()
        p = _policy(
            "p",
            [
                _rule("r1", "score", ComparisonOperator.GT, 0.5, "block"),
                _rule("r2", "score", ComparisonOperator.GT, 0.5, "allow"),
            ],
        )
        conflicts = detector.detect_internal_conflicts(p)
        assert len(conflicts) >= 1

    def test_resolution_strategy(self):
        detector = ConflictDetector(resolution=ConflictResolution.MOST_RESTRICTIVE)
        r1 = _rule("r1", "score", ComparisonOperator.GT, 0.5, "block")
        r2 = _rule("r2", "score", ComparisonOperator.GT, 0.5, "allow")
        conflicts = detector.detect_rule_conflicts([r1], [r2])
        assert conflicts[0].resolution == ConflictResolution.MOST_RESTRICTIVE

    def test_no_rules_no_conflicts(self):
        detector = ConflictDetector()
        conflicts = detector.detect_rule_conflicts([], [])
        assert len(conflicts) == 0

    def test_multiple_conflicts(self):
        detector = ConflictDetector()
        r1 = _rule("r1", "score", ComparisonOperator.GT, 0.5, "block")
        r2 = _rule("r2", "score", ComparisonOperator.GT, 0.5, "allow")
        r3 = _rule("r3", "confidence", ComparisonOperator.GT, 0.5, "block")
        r4 = _rule("r4", "confidence", ComparisonOperator.GT, 0.5, "warn")
        conflicts = detector.detect_rule_conflicts([r1, r3], [r2, r4])
        assert len(conflicts) == 2
