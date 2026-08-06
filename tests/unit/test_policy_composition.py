"""Tests for Policy Composition (templates, inheritance, merge)."""

from q_guardian.policy.composition import PolicyComposer
from q_guardian.policy.data import AdvancedPolicyDefinition, AdvancedRule, Condition
from q_guardian.policy.enums import ComparisonOperator


def _policy(name: str, **kwargs) -> AdvancedPolicyDefinition:
    return AdvancedPolicyDefinition(
        name=name,
        rules=[
            AdvancedRule(
                name=f"{name}-rule",
                condition=Condition(field="score", operator=ComparisonOperator.GT, value=0.5),
                action="block",
            )
        ],
        **kwargs,
    )


class TestPolicyComposer:
    def test_register_template(self):
        composer = PolicyComposer()
        template = _policy("template-1")
        composer.register_template(template)
        assert composer.get_template(template.policy_id) is not None

    def test_list_templates(self):
        composer = PolicyComposer()
        composer.register_template(_policy("t1"))
        composer.register_template(_policy("t2"))
        assert len(composer.list_templates()) == 2

    def test_get_template_not_found(self):
        composer = PolicyComposer()
        assert composer.get_template("nonexistent") is None

    def test_inherit(self):
        composer = PolicyComposer()
        parent = _policy("parent")
        child = composer.inherit(parent, "child")
        assert child.name == "child"
        assert child.parent_policy_id == parent.policy_id

    def test_inherit_with_overrides(self):
        composer = PolicyComposer()
        parent = _policy("parent", description="original")
        child = composer.inherit(parent, "child", overrides={"description": "overridden"})
        assert child.description == "overridden"

    def test_inherit_with_rule_overrides(self):
        composer = PolicyComposer()
        parent = _policy("parent")
        parent.rules[0].name = "target-rule"
        child = composer.inherit(
            parent,
            "child",
            rule_overrides=[{"match_by": "name", "match_value": "target-rule", "action": "warn"}],
        )
        assert child.rules[0].action == "warn"

    def test_inherit_by_action_override(self):
        composer = PolicyComposer()
        parent = _policy("parent")
        child = composer.inherit(
            parent,
            "child",
            rule_overrides=[{"match_by": "action", "match_value": "block", "action": "log"}],
        )
        assert child.rules[0].action == "log"

    def test_inherit_by_index_override(self):
        composer = PolicyComposer()
        parent = _policy("parent")
        child = composer.inherit(
            parent,
            "child",
            rule_overrides=[{"match_by": "index", "match_value": "0", "severity": "critical"}],
        )
        assert child.rules[0].severity == "critical"

    def test_merge_override_strategy(self):
        composer = PolicyComposer()
        p1 = _policy("p1")
        p1.rules[0].name = "shared-rule"
        p2 = _policy("p2")
        p2.rules[0].name = "shared-rule"
        p2.rules[0].action = "warn"
        merged = composer.merge(p1, p2, strategy="override")
        assert merged.rules[0].action == "warn"

    def test_merge_append_strategy(self):
        composer = PolicyComposer()
        p1 = _policy("p1")
        p2 = _policy("p2")
        merged = composer.merge(p1, p2, strategy="append")
        assert len(merged.rules) == 2

    def test_merge_interleave_strategy(self):
        composer = PolicyComposer()
        r1 = AdvancedRule(
            name="r1",
            condition=Condition(field="x", operator=ComparisonOperator.GT, value=1),
            action="block",
            priority=5,
        )
        r2 = AdvancedRule(
            name="r2",
            condition=Condition(field="y", operator=ComparisonOperator.GT, value=1),
            action="warn",
            priority=1,
        )
        p1 = AdvancedPolicyDefinition(name="p1", rules=[r1])
        p2 = AdvancedPolicyDefinition(name="p2", rules=[r2])
        merged = composer.merge(p1, p2, strategy="interleave")
        assert merged.rules[0].priority == 1
        assert merged.rules[1].priority == 5

    def test_apply_template(self):
        composer = PolicyComposer()
        template = AdvancedPolicyDefinition(
            name="template",
            description="Policy for ${env} environment",
            rules=[
                AdvancedRule(
                    name="${action}-rule",
                    condition=Condition(field="x", operator=ComparisonOperator.GT, value=1),
                    action="block",
                )
            ],
        )
        result = composer.apply_template(
            template, "prod-policy", context={"env": "production", "action": "block"}
        )
        assert result.name == "prod-policy"
        assert "production" in result.description

    def test_inheritance_chain(self):
        composer = PolicyComposer()
        grandparent = _policy("gp")
        parent = _policy("p")
        parent.parent_policy_id = grandparent.policy_id
        child = _policy("c")
        child.parent_policy_id = parent.policy_id

        all_policies = {
            grandparent.policy_id: grandparent,
            parent.policy_id: parent,
        }
        chain = composer.get_inheritance_chain(child, all_policies)
        assert len(chain) == 2
        assert chain[0] == parent.policy_id
        assert chain[1] == grandparent.policy_id

    def test_inheritance_chain_with_cycle(self):
        composer = PolicyComposer()
        p1 = _policy("p1")
        p2 = _policy("p2")
        p1.parent_policy_id = p2.policy_id
        p2.parent_policy_id = p1.policy_id
        chain = composer.get_inheritance_chain(p1, {"p1_id": p1, "p2_id": p2})
        # Should handle cycle gracefully
        assert isinstance(chain, list)

    def test_inherit_deep_copies(self):
        composer = PolicyComposer()
        parent = _policy("parent")
        child = composer.inherit(parent, "child")
        parent.name = "modified"
        assert child.name == "child"
