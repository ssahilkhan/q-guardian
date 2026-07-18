"""PolicyRegistry — manages policy registration and lookup."""

from __future__ import annotations

import structlog

from q_guardian.risk.data import PolicyDefinition
from q_guardian.risk.exceptions import PolicyNotFoundError

logger = structlog.get_logger("risk.policy_registry")


class PolicyRegistry:
    """Central registry for policy definitions.

    Policies are registered by name and can be retrieved, updated,
    or removed at runtime.
    """

    def __init__(self) -> None:
        self._policies: dict[str, PolicyDefinition] = {}

    @property
    def count(self) -> int:
        return len(self._policies)

    def register(self, policy: PolicyDefinition) -> None:
        """Register a policy definition.

        Args:
            policy: The policy to register.

        Raises:
            ValueError: If a policy with the same name already exists.
        """
        if policy.name in self._policies:
            raise ValueError(f"Policy '{policy.name}' is already registered")
        self._policies[policy.name] = policy
        logger.info("policy_registered", policy_name=policy.name, rules=len(policy.rules))

    def unregister(self, name: str) -> bool:
        """Remove a policy by name.

        Returns:
            True if the policy was found and removed.
        """
        if name in self._policies:
            del self._policies[name]
            logger.info("policy_unregistered", policy_name=name)
            return True
        return False

    def get(self, name: str) -> PolicyDefinition:
        """Get a policy by name.

        Raises:
            PolicyNotFoundError: If the policy does not exist.
        """
        if name not in self._policies:
            raise PolicyNotFoundError(policy_name=name)
        return self._policies[name]

    def has(self, name: str) -> bool:
        """Check if a policy is registered."""
        return name in self._policies

    def list_policies(self) -> list[PolicyDefinition]:
        """List all registered policies."""
        return list(self._policies.values())

    def list_enabled(self) -> list[PolicyDefinition]:
        """List all enabled policies."""
        return [p for p in self._policies.values() if p.enabled]

    def enable(self, name: str) -> None:
        """Enable a policy."""
        if name in self._policies:
            self._policies[name].enabled = True
            logger.info("policy_enabled", policy_name=name)

    def disable(self, name: str) -> None:
        """Disable a policy."""
        if name in self._policies:
            self._policies[name].enabled = False
            logger.info("policy_disabled", policy_name=name)

    def update(self, policy: PolicyDefinition) -> None:
        """Update an existing policy (or register if new)."""
        self._policies[policy.name] = policy
        logger.info("policy_updated", policy_name=policy.name)
