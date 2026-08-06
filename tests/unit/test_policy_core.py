"""Tests for Module 8: Policy enums, data models, config, events, exceptions."""

from datetime import UTC, datetime

from q_guardian.policy.config import PolicyEngineConfig
from q_guardian.policy.data import (
    AdvancedPolicyDefinition,
    AdvancedRule,
    CompoundCondition,
    Condition,
    ConflictResult,
    DSLAdapterResult,
    PolicyEvaluationResult,
    PolicyVersion,
    RBACPermission,
    SimulationResult,
)
from q_guardian.policy.enums import (
    ComparisonOperator,
    ConditionType,
    ConflictResolution,
    ConflictType,
    DSLFormat,
    LogicalOperator,
    Permission,
    PolicyStatus,
)
from q_guardian.policy.events import (
    PolicyActivated,
    PolicyConflictDetected,
    PolicyDeactivated,
    PolicyEvaluated,
    PolicyRegistered,
    PolicySimulated,
    PolicyUpdated,
)
from q_guardian.policy.exceptions import (
    ConditionParseError,
    DSLAdapterError,
    PolicyCompositionError,
    PolicyConflictError,
    PolicyEngineError,
    PolicyNotFoundError,
    PolicyVersionError,
    RBACError,
    SimulationError,
)


class TestEnums:
    def test_comparison_operators(self):
        assert ComparisonOperator.EQ.value == "=="
        assert ComparisonOperator.NEQ.value == "!="
        assert ComparisonOperator.GT.value == ">"
        assert ComparisonOperator.GTE.value == ">="
        assert ComparisonOperator.LT.value == "<"
        assert ComparisonOperator.LTE.value == "<="
        assert ComparisonOperator.MATCHES.value == "=~"
        assert ComparisonOperator.NOT_MATCHES.value == "!~"
        assert ComparisonOperator.IN.value == "in"
        assert ComparisonOperator.NOT_IN.value == "not_in"
        assert ComparisonOperator.CONTAINS.value == "contains"
        assert ComparisonOperator.STARTS_WITH.value == "starts_with"
        assert ComparisonOperator.ENDS_WITH.value == "ends_with"

    def test_logical_operators(self):
        assert LogicalOperator.AND.value == "and"
        assert LogicalOperator.OR.value == "or"
        assert LogicalOperator.NOT.value == "not"

    def test_condition_types(self):
        assert ConditionType.COMPARISON.value == "comparison"
        assert ConditionType.COMPOUND.value == "compound"
        assert ConditionType.TEMPORAL.value == "temporal"
        assert ConditionType.REGEX.value == "regex"
        assert ConditionType.EXISTS.value == "exists"

    def test_policy_status(self):
        assert PolicyStatus.DRAFT.value == "draft"
        assert PolicyStatus.ACTIVE.value == "active"
        assert PolicyStatus.SUSPENDED.value == "suspended"
        assert PolicyStatus.RETIRED.value == "retired"
        assert PolicyStatus.DELETED.value == "deleted"

    def test_conflict_type(self):
        assert ConflictType.OVERLAPPING.value == "overlapping"
        assert ConflictType.SHADOWED.value == "shadowed"
        assert ConflictType.CONTRADICTING.value == "contradicting"
        assert ConflictType.REDUNDANT.value == "redundant"

    def test_conflict_resolution(self):
        assert ConflictResolution.PRIORITY.value == "priority"
        assert ConflictResolution.MOST_RESTRICTIVE.value == "most_restrictive"
        assert ConflictResolution.MOST_PERMISSIVE.value == "most_permissive"
        assert ConflictResolution.FIRST_MATCH.value == "first_match"
        assert ConflictResolution.MANUAL.value == "manual"

    def test_dsl_format(self):
        assert DSLFormat.REGO.value == "rego"
        assert DSLFormat.CEDAR.value == "cedar"
        assert DSLFormat.YAML.value == "yaml"
        assert DSLFormat.JSON.value == "json"
        assert DSLFormat.CUSTOM.value == "custom"

    def test_permission(self):
        assert Permission.POLICY_CREATE.value == "policy_create"
        assert Permission.POLICY_READ.value == "policy_read"
        assert Permission.POLICY_UPDATE.value == "policy_update"
        assert Permission.POLICY_DELETE.value == "policy_delete"
        assert Permission.POLICY_EVALUATE.value == "policy_evaluate"
        assert Permission.POLICY_ACTIVATE.value == "policy_activate"
        assert Permission.POLICY_DEACTIVATE.value == "policy_deactivate"
        assert Permission.POLICY_SIMULATE.value == "policy_simulate"
        assert Permission.POLICY_EXPORT.value == "policy_export"
        assert Permission.POLICY_IMPORT.value == "policy_import"
        assert Permission.POLICY_ADMIN.value == "policy_admin"


class TestCondition:
    def test_eq_comparison(self):
        c = Condition(field="risk_score", operator=ComparisonOperator.EQ, value=0.9)
        assert c.evaluate({"risk_score": 0.9}) is True
        assert c.evaluate({"risk_score": 0.8}) is False

    def test_neq_comparison(self):
        c = Condition(field="level", operator=ComparisonOperator.NEQ, value="low")
        assert c.evaluate({"level": "high"}) is True
        assert c.evaluate({"level": "low"}) is False

    def test_gt_comparison(self):
        c = Condition(field="score", operator=ComparisonOperator.GT, value=0.5)
        assert c.evaluate({"score": 0.8}) is True
        assert c.evaluate({"score": 0.3}) is False

    def test_gte_comparison(self):
        c = Condition(field="score", operator=ComparisonOperator.GTE, value=0.5)
        assert c.evaluate({"score": 0.5}) is True
        assert c.evaluate({"score": 0.4}) is False

    def test_lt_comparison(self):
        c = Condition(field="score", operator=ComparisonOperator.LT, value=0.5)
        assert c.evaluate({"score": 0.3}) is True
        assert c.evaluate({"score": 0.8}) is False

    def test_lte_comparison(self):
        c = Condition(field="score", operator=ComparisonOperator.LTE, value=0.5)
        assert c.evaluate({"score": 0.5}) is True
        assert c.evaluate({"score": 0.6}) is False

    def test_matches_regex(self):
        c = Condition(field="name", operator=ComparisonOperator.MATCHES, value="test_.*")
        assert c.evaluate({"name": "test_user"}) is True
        assert c.evaluate({"name": "prod_user"}) is False

    def test_not_matches_regex(self):
        c = Condition(field="name", operator=ComparisonOperator.NOT_MATCHES, value="test_.*")
        assert c.evaluate({"name": "prod_user"}) is True
        assert c.evaluate({"name": "test_user"}) is False

    def test_in_operator(self):
        c = Condition(field="level", operator=ComparisonOperator.IN, value=["high", "critical"])
        assert c.evaluate({"level": "high"}) is True
        assert c.evaluate({"level": "low"}) is False

    def test_not_in_operator(self):
        c = Condition(field="level", operator=ComparisonOperator.NOT_IN, value=["low", "medium"])
        assert c.evaluate({"level": "high"}) is True
        assert c.evaluate({"level": "low"}) is False

    def test_contains_operator(self):
        c = Condition(field="msg", operator=ComparisonOperator.CONTAINS, value="error")
        assert c.evaluate({"msg": "an error occurred"}) is True
        assert c.evaluate({"msg": "all good"}) is False

    def test_starts_with_operator(self):
        c = Condition(field="path", operator=ComparisonOperator.STARTS_WITH, value="/api")
        assert c.evaluate({"path": "/api/v1"}) is True
        assert c.evaluate({"path": "/web"}) is False

    def test_ends_with_operator(self):
        c = Condition(field="path", operator=ComparisonOperator.ENDS_WITH, value=".py")
        assert c.evaluate({"path": "test.py"}) is True
        assert c.evaluate({"path": "test.js"}) is False

    def test_negated_condition(self):
        c = Condition(field="score", operator=ComparisonOperator.GT, value=0.5, negated=True)
        assert c.evaluate({"score": 0.8}) is False
        assert c.evaluate({"score": 0.3}) is True

    def test_missing_field_returns_false(self):
        c = Condition(field="missing", operator=ComparisonOperator.GT, value=0.5)
        assert c.evaluate({}) is False

    def test_eq_neq_with_missing_field(self):
        c = Condition(field="missing", operator=ComparisonOperator.EQ, value="x")
        assert c.evaluate({}) is False
        c2 = Condition(field="missing", operator=ComparisonOperator.NEQ, value="x")
        assert c2.evaluate({}) is True

    def test_condition_id_auto_generated(self):
        c = Condition(field="x", operator=ComparisonOperator.EQ, value=1)
        assert c.condition_id  # non-empty

    def test_condition_type_default(self):
        c = Condition(field="x", operator=ComparisonOperator.EQ, value=1)
        assert c.condition_type == ConditionType.COMPARISON

    def test_condition_metadata(self):
        c = Condition(field="x", operator=ComparisonOperator.EQ, value=1, metadata={"key": "val"})
        assert c.metadata == {"key": "val"}


class TestCompoundCondition:
    def test_and_operator(self):
        c = CompoundCondition(
            operator=LogicalOperator.AND,
            conditions=[
                Condition(field="a", operator=ComparisonOperator.GT, value=5),
                Condition(field="b", operator=ComparisonOperator.LT, value=10),
            ],
        )
        assert c.evaluate({"a": 7, "b": 8}) is True
        assert c.evaluate({"a": 3, "b": 8}) is False
        assert c.evaluate({"a": 7, "b": 12}) is False

    def test_or_operator(self):
        c = CompoundCondition(
            operator=LogicalOperator.OR,
            conditions=[
                Condition(field="a", operator=ComparisonOperator.GT, value=5),
                Condition(field="b", operator=ComparisonOperator.LT, value=10),
            ],
        )
        assert c.evaluate({"a": 7, "b": 12}) is True
        assert c.evaluate({"a": 3, "b": 12}) is False

    def test_not_operator(self):
        c = CompoundCondition(
            operator=LogicalOperator.NOT,
            conditions=[
                Condition(field="a", operator=ComparisonOperator.EQ, value=1),
            ],
        )
        assert c.evaluate({"a": 2}) is True
        assert c.evaluate({"a": 1}) is False

    def test_nested_compound(self):
        c = CompoundCondition(
            operator=LogicalOperator.AND,
            conditions=[
                CompoundCondition(
                    operator=LogicalOperator.OR,
                    conditions=[
                        Condition(field="a", operator=ComparisonOperator.EQ, value=1),
                        Condition(field="b", operator=ComparisonOperator.EQ, value=2),
                    ],
                ),
                Condition(field="c", operator=ComparisonOperator.EQ, value=3),
            ],
        )
        assert c.evaluate({"a": 1, "c": 3}) is True
        assert c.evaluate({"b": 2, "c": 3}) is True
        assert c.evaluate({"a": 1, "b": 2}) is False  # c != 3

    def test_empty_conditions_returns_true(self):
        c = CompoundCondition(operator=LogicalOperator.AND, conditions=[])
        assert c.evaluate({}) is True

    def test_compound_condition_id_auto_generated(self):
        c = CompoundCondition(operator=LogicalOperator.AND)
        assert c.condition_id


class TestAdvancedRule:
    def test_rule_creation(self):
        rule = AdvancedRule(
            name="test-rule",
            condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
            action="block",
            severity="high",
            priority=10,
        )
        assert rule.name == "test-rule"
        assert rule.action == "block"
        assert rule.priority == 10
        assert rule.enabled is True

    def test_rule_evaluate(self):
        rule = AdvancedRule(
            condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
            action="block",
        )
        assert rule.evaluate({"score": 0.8}) is True
        assert rule.evaluate({"score": 0.3}) is False

    def test_disabled_rule_returns_false(self):
        rule = AdvancedRule(
            condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
            action="block",
            enabled=False,
        )
        assert rule.evaluate({"score": 0.8}) is False

    def test_temporal_rule_valid(self):
        rule = AdvancedRule(
            condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
            action="block",
            valid_from=datetime(2020, 1, 1, tzinfo=UTC),
            valid_until=datetime(2030, 12, 31, tzinfo=UTC),
        )
        assert rule.evaluate({"score": 0.8}) is True
        assert rule.is_temporal() is True

    def test_temporal_rule_expired(self):
        rule = AdvancedRule(
            condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
            action="block",
            valid_from=datetime(2020, 1, 1, tzinfo=UTC),
            valid_until=datetime(2021, 1, 1, tzinfo=UTC),
        )
        assert rule.evaluate({"score": 0.8}) is False

    def test_rule_action_params(self):
        rule = AdvancedRule(
            condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
            action="webhook",
            action_params={"url": "https://example.com", "timeout": 30},
        )
        assert rule.action_params["url"] == "https://example.com"

    def test_rule_tags(self):
        rule = AdvancedRule(
            condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
            action="block",
            tags=["security", "critical"],
        )
        assert "security" in rule.tags


class TestAdvancedPolicyDefinition:
    def test_policy_creation(self):
        policy = AdvancedPolicyDefinition(
            name="test-policy",
            description="A test policy",
            rules=[
                AdvancedRule(
                    condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
                    action="block",
                )
            ],
        )
        assert policy.name == "test-policy"
        assert len(policy.rules) == 1
        assert policy.status == PolicyStatus.DRAFT

    def test_enabled_rules(self):
        policy = AdvancedPolicyDefinition(
            name="test",
            rules=[
                AdvancedRule(
                    condition=Condition(field="a", operator=ComparisonOperator.EQ, value=1),
                    action="allow",
                    enabled=True,
                ),
                AdvancedRule(
                    condition=Condition(field="b", operator=ComparisonOperator.EQ, value=2),
                    action="block",
                    enabled=False,
                ),
            ],
        )
        assert len(policy.enabled_rules()) == 1

    def test_policy_parent(self):
        child = AdvancedPolicyDefinition(
            name="child",
            parent_policy_id="parent-123",
        )
        assert child.parent_policy_id == "parent-123"

    def test_policy_timestamps(self):
        policy = AdvancedPolicyDefinition(name="test")
        assert policy.created_at is not None
        assert policy.updated_at is not None

    def test_policy_defaults(self):
        policy = AdvancedPolicyDefinition(name="test")
        assert policy.version == "1.0.0"
        assert policy.default_action == "allow"
        assert policy.default_severity == "low"
        assert policy.tags == []


class TestPolicyVersion:
    def test_version_creation(self):
        policy = AdvancedPolicyDefinition(name="test")
        pv = PolicyVersion(
            policy_id=policy.policy_id,
            version="1.0.0",
            policy_snapshot=policy,
            changelog="Initial version",
        )
        assert pv.version == "1.0.0"
        assert pv.changelog == "Initial version"

    def test_version_timestamp(self):
        pv = PolicyVersion(
            policy_id="x", version="1.0.0", policy_snapshot=AdvancedPolicyDefinition(name="x")
        )
        assert pv.created_at is not None


class TestConflictResult:
    def test_conflict_creation(self):
        cr = ConflictResult(
            conflict_type=ConflictType.OVERLAPPING,
            rule_id_a="r1",
            rule_id_b="r2",
            description="Test conflict",
        )
        assert cr.conflict_type == ConflictType.OVERLAPPING
        assert cr.resolved is False


class TestSimulationResult:
    def test_simulation_creation(self):
        sr = SimulationResult(
            policy_id="p1",
            policy_name="test",
            input_context={"score": 0.9},
            action="block",
        )
        assert sr.policy_name == "test"
        assert sr.would_execute is True


class TestPolicyEvaluationResult:
    def test_evaluation_creation(self):
        per = PolicyEvaluationResult(
            policy_id="p1",
            policy_name="test",
            action="block",
            matched_rules=["r1"],
        )
        assert per.matched_rules == ["r1"]


class TestRBACPermission:
    def test_rbac_permission(self):
        rp = RBACPermission(
            role="admin",
            permissions=[Permission.POLICY_CREATE, Permission.POLICY_DELETE],
        )
        assert len(rp.permissions) == 2


class TestDSLAdapterResult:
    def test_adapter_result(self):
        dar = DSLAdapterResult(
            source_format=DSLFormat.REGO,
            raw_source="package test",
            success=True,
        )
        assert dar.success is True


class TestPolicyEngineConfig:
    def test_default_config(self):
        config = PolicyEngineConfig()
        assert config.evaluation_timeout_seconds == 5.0
        assert config.max_rules_per_policy == 1000
        assert config.enable_versioning is True
        assert config.enable_simulation is True
        assert config.enable_rbac is False
        assert config.enable_composition is True

    def test_custom_config(self):
        config = PolicyEngineConfig(
            evaluation_timeout_seconds=10.0,
            enable_rbac=True,
            persist_to_file=True,
        )
        assert config.evaluation_timeout_seconds == 10.0
        assert config.enable_rbac is True
        assert config.persist_to_file is True


class TestEvents:
    def test_policy_registered_event(self):
        e = PolicyRegistered(policy_id="p1", policy_name="test", version="1.0.0")
        assert e.policy_name == "test"
        assert e.timestamp is not None

    def test_policy_updated_event(self):
        e = PolicyUpdated(policy_id="p1", old_version="1.0.0", new_version="1.1.0")
        assert e.old_version == "1.0.0"

    def test_policy_evaluated_event(self):
        e = PolicyEvaluated(policy_id="p1", action="block", matched_rules=["r1"])
        assert e.action == "block"

    def test_policy_conflict_event(self):
        e = PolicyConflictDetected(conflict_type="overlapping", rule_id_a="r1", rule_id_b="r2")
        assert e.conflict_type == "overlapping"

    def test_policy_simulated_event(self):
        e = PolicySimulated(policy_id="p1", action="warn", would_execute=False)
        assert e.would_execute is False

    def test_policy_activated_event(self):
        e = PolicyActivated(policy_id="p1", policy_name="test")
        assert e.policy_name == "test"

    def test_policy_deactivated_event(self):
        e = PolicyDeactivated(policy_id="p1", reason="expired")
        assert e.reason == "expired"


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(ConditionParseError, PolicyEngineError)
        assert issubclass(PolicyConflictError, PolicyEngineError)
        assert issubclass(PolicyVersionError, PolicyEngineError)
        assert issubclass(SimulationError, PolicyEngineError)
        assert issubclass(DSLAdapterError, PolicyEngineError)
        assert issubclass(RBACError, PolicyEngineError)
        assert issubclass(PolicyNotFoundError, PolicyEngineError)
        assert issubclass(PolicyCompositionError, PolicyEngineError)

    def test_exception_details(self):
        e = PolicyEngineError("test", details={"key": "val"})
        assert e.details == {"key": "val"}
        assert str(e) == "test"
