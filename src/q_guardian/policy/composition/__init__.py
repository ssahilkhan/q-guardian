"""Policy Composition — templates, inheritance, and overrides."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.policy.exceptions import PolicyCompositionError

if TYPE_CHECKING:
    from q_guardian.policy.data import AdvancedPolicyDefinition

logger = structlog.get_logger(__name__)


class PolicyComposer:
    """Composes policies through templates, inheritance, and overrides."""

    def __init__(self, max_inheritance_depth: int = 5) -> None:
        self._templates: dict[str, AdvancedPolicyDefinition] = {}
        self._max_depth = max_inheritance_depth

    def register_template(self, template: AdvancedPolicyDefinition) -> None:
        self._templates[template.policy_id] = template
        logger.info("template_registered", template_id=template.policy_id, name=template.name)

    def get_template(self, template_id: str) -> AdvancedPolicyDefinition | None:
        return self._templates.get(template_id)

    def list_templates(self) -> list[AdvancedPolicyDefinition]:
        return list(self._templates.values())

    def inherit(
        self,
        parent: AdvancedPolicyDefinition,
        child_name: str,
        overrides: dict[str, Any] | None = None,
        rule_overrides: list[dict[str, Any]] | None = None,
    ) -> AdvancedPolicyDefinition:
        """Create a child policy inheriting from a parent with optional overrides."""
        # Check inheritance depth
        depth = self._calc_inheritance_depth(parent)
        if depth >= self._max_depth:
            raise PolicyCompositionError(f"Maximum inheritance depth ({self._max_depth}) exceeded")

        child = parent.model_copy(deep=True)
        child.policy_id = ""  # will be regenerated
        child.name = child_name
        child.parent_policy_id = parent.policy_id
        child.created_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        child.updated_at = child.created_at

        # Apply field overrides
        if overrides:
            for key, value in overrides.items():
                if hasattr(child, key):
                    setattr(child, key, value)

        # Apply rule overrides (match by rule name or index)
        if rule_overrides:
            for ro in rule_overrides:
                self._apply_rule_override(child, ro)

        logger.info(
            "policy_inherited",
            parent_id=parent.policy_id,
            child_name=child_name,
        )
        return child

    def merge(
        self,
        base: AdvancedPolicyDefinition,
        overlay: AdvancedPolicyDefinition,
        strategy: str = "override",
    ) -> AdvancedPolicyDefinition:
        """Merge two policies. Strategy: 'override', 'append', 'interleave'."""
        merged = base.model_copy(deep=True)
        merged.policy_id = ""
        merged.name = f"{base.name}+{overlay.name}"
        merged.description = f"Merged from {base.name} and {overlay.name}"

        if strategy == "override":
            # Overlay rules take precedence by same name
            base_rule_names = {r.name: i for i, r in enumerate(merged.rules)}
            for rule in overlay.rules:
                if rule.name in base_rule_names:
                    idx = base_rule_names[rule.name]
                    merged.rules[idx] = rule.model_copy(deep=True)
                else:
                    merged.rules.append(rule.model_copy(deep=True))

        elif strategy == "append":
            merged.rules.extend(overlay.rules)

        elif strategy == "interleave":
            # Interleave by priority
            all_rules = merged.rules + overlay.rules
            all_rules.sort(key=lambda r: r.priority)
            merged.rules = all_rules

        logger.info(
            "policies_merged",
            base_name=base.name,
            overlay_name=overlay.name,
            strategy=strategy,
            final_rule_count=len(merged.rules),
        )
        return merged

    def apply_template(
        self,
        template: AdvancedPolicyDefinition,
        policy_name: str,
        context: dict[str, Any] | None = None,
    ) -> AdvancedPolicyDefinition:
        """Apply a template to create a new policy with optional variable substitution."""
        policy = template.model_copy(deep=True)
        policy.policy_id = ""
        policy.name = policy_name

        # Simple variable substitution in descriptions and rule names
        if context:
            for key, value in context.items():
                placeholder = f"${{{key}}}"
                policy.description = policy.description.replace(placeholder, str(value))
                for rule in policy.rules:
                    rule.name = rule.name.replace(placeholder, str(value))
                    rule.description = rule.description.replace(placeholder, str(value))

        logger.info(
            "template_applied",
            template_id=template.policy_id,
            policy_name=policy_name,
        )
        return policy

    def get_inheritance_chain(
        self,
        policy: AdvancedPolicyDefinition,
        all_policies: dict[str, AdvancedPolicyDefinition],
    ) -> list[str]:
        """Get the full inheritance chain (list of policy IDs)."""
        chain: list[str] = []
        current = policy
        visited: set[str] = set()

        while current.parent_policy_id and current.parent_policy_id not in visited:
            chain.append(current.parent_policy_id)
            visited.add(current.parent_policy_id)
            parent = all_policies.get(current.parent_policy_id)
            if parent is None:
                break
            current = parent

        return chain

    @staticmethod
    def _calc_inheritance_depth(policy: AdvancedPolicyDefinition) -> int:
        depth = 0
        current = policy
        visited: set[str] = set()
        while current.parent_policy_id and current.parent_policy_id not in visited:
            depth += 1
            visited.add(current.parent_policy_id)
            # Can't follow references without a registry, so we count placeholders
            break
        return depth

    @staticmethod
    def _apply_rule_override(
        policy: AdvancedPolicyDefinition,
        override: dict[str, Any],
    ) -> None:
        """Apply a rule override by matching name or index."""
        match_by = override.get("match_by", "name")
        match_value = override.get("match_value", "")

        for i, rule in enumerate(policy.rules):
            matched = False
            if (
                (match_by == "name" and rule.name == match_value)
                or (match_by == "index" and i == int(match_value))
                or (match_by == "action" and rule.action == match_value)
            ):
                matched = True

            if matched:
                for key in ("action", "severity", "priority", "enabled", "action_params"):
                    if key in override:
                        setattr(rule, key, override[key])
