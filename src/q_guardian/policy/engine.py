"""Advanced Policy Engine — main orchestrator tying all components together."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog

from q_guardian.policy.config import PolicyEngineConfig
from q_guardian.policy.core.condition_parser import parse_condition
from q_guardian.policy.core.conflict_detector import ConflictDetector
from q_guardian.policy.core.evaluator import PolicyEvaluator
from q_guardian.policy.core.registry import PolicyRegistry
from q_guardian.policy.core.simulation import SimulationEngine
from q_guardian.policy.core.version_manager import VersionManager
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
    PolicyConflictError,
    PolicyEngineError,
    PolicyNotFoundError,
)

if TYPE_CHECKING:
    from q_guardian.policy.data import (
        AdvancedPolicyDefinition,
        CompoundCondition,
        Condition,
        ConflictResult,
        DSLAdapterResult,
        PolicyEvaluationResult,
        SimulationResult,
    )
    from q_guardian.policy.enums import (
        DSLFormat,
        Permission,
    )

logger = structlog.get_logger(__name__)


class AdvancedPolicyEngine:
    """Full-featured policy engine with advanced conditions, versioning,
    conflict detection, simulation, DSL adapters, RBAC, and composition.
    """

    def __init__(self, config: PolicyEngineConfig | None = None) -> None:
        self._config = config or PolicyEngineConfig()

        # Core components
        self._registry = PolicyRegistry(
            storage_path=self._config.storage_path if self._config.persist_to_file else None
        )
        self._evaluator = PolicyEvaluator(timeout_seconds=self._config.evaluation_timeout_seconds)
        self._conflict_detector = ConflictDetector(
            resolution=self._config.default_conflict_resolution
        )
        self._version_manager = VersionManager(max_versions=self._config.max_versions_per_policy)
        self._simulation_engine = SimulationEngine(evaluator=self._evaluator)

        # Optional components (initialized lazily)
        self._rbac: Any = None
        self._composer: Any = None
        self._events: list[Any] = []

    # ------------------------------------------------------------------
    # Registry operations
    # ------------------------------------------------------------------

    def register_policy(
        self,
        policy: AdvancedPolicyDefinition,
        created_by: str = "",
    ) -> None:
        """Register a new policy with optional conflict detection."""
        if self._config.enable_rbac and self._rbac:
            # RBAC check would go here; for now just log
            pass

        # Auto-detect conflicts
        if self._config.auto_detect_conflicts:
            existing = self._registry.list_policies()
            for other in existing:
                conflicts = self._conflict_detector.detect_policy_conflicts(policy, other)
                for conflict in conflicts:
                    self._events.append(
                        PolicyConflictDetected(
                            conflict_type=conflict.conflict_type.value,
                            rule_id_a=conflict.rule_id_a,
                            rule_id_b=conflict.rule_id_b,
                            policy_id_a=conflict.policy_id_a,
                            policy_id_b=conflict.policy_id_b,
                        )
                    )
                    if not self._config.allow_overlapping_rules:
                        raise PolicyConflictError(
                            f"Conflicting rules detected: {conflict.description}"
                        )

        policy.created_by = created_by
        self._registry.register(policy)

        # Create initial version snapshot
        if self._config.enable_versioning:
            self._version_manager.create_snapshot(
                policy, changelog="Initial registration", created_by=created_by
            )

        self._events.append(
            PolicyRegistered(
                policy_id=policy.policy_id,
                policy_name=policy.name,
                version=policy.version,
            )
        )
        logger.info("policy_registered", policy_id=policy.policy_id, name=policy.name)

    def update_policy(
        self,
        policy: AdvancedPolicyDefinition,
        changelog: str = "",
        created_by: str = "",
        bump: str = "patch",
    ) -> None:
        """Update a policy with version snapshot."""
        if self._config.enable_versioning:
            self._version_manager.create_snapshot(
                policy, changelog=changelog, created_by=created_by
            )
            self._version_manager.bump_version(policy, level=bump)

        self._registry.update(policy)
        self._events.append(
            PolicyUpdated(
                policy_id=policy.policy_id,
                policy_name=policy.name,
                new_version=policy.version,
            )
        )

    def activate_policy(self, policy_id: str) -> None:
        self._registry.activate(policy_id)
        policy = self._registry.get(policy_id)
        self._events.append(PolicyActivated(policy_id=policy_id, policy_name=policy.name))

    def deactivate_policy(self, policy_id: str) -> None:
        self._registry.deactivate(policy_id)
        policy = self._registry.get(policy_id)
        self._events.append(PolicyDeactivated(policy_id=policy_id, policy_name=policy.name))

    def get_policy(self, policy_id: str) -> AdvancedPolicyDefinition:
        return self._registry.get(policy_id)

    def list_policies(self) -> list[AdvancedPolicyDefinition]:
        return self._registry.list_policies()

    def list_active_policies(self) -> list[AdvancedPolicyDefinition]:
        return self._registry.list_active()

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        context: dict[str, Any],
        policy_id: str | None = None,
    ) -> PolicyEvaluationResult:
        """Evaluate a policy (or all active policies) against a context."""
        start = time.monotonic()

        if policy_id:
            policy = self._registry.get(policy_id)
            result = self._evaluator.evaluate(policy, context)
        else:
            active = self._registry.list_active()
            if not active:
                raise PolicyNotFoundError("No active policies found")
            # Evaluate against first active policy
            result = self._evaluator.evaluate(active[0], context)

        result.execution_time_ms = (time.monotonic() - start) * 1000

        self._events.append(
            PolicyEvaluated(
                policy_id=result.policy_id,
                policy_name=result.policy_name,
                action=result.action,
                matched_rules=result.matched_rules,
                execution_time_ms=result.execution_time_ms,
            )
        )

        if self._config.log_evaluations:
            logger.info(
                "policy_evaluated",
                policy_id=result.policy_id,
                action=result.action,
                matched_count=len(result.matched_rules),
            )

        return result

    def evaluate_all(
        self,
        context: dict[str, Any],
    ) -> list[PolicyEvaluationResult]:
        """Evaluate all active policies against a context."""
        results: list[PolicyEvaluationResult] = []
        for policy in self._registry.list_active():
            result = self._evaluator.evaluate(policy, context)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def simulate(
        self,
        policy_id: str,
        context: dict[str, Any],
    ) -> SimulationResult:
        """Dry-run evaluation of a policy."""
        if not self._config.enable_simulation:
            raise PolicyEngineError("Simulation is disabled")
        policy = self._registry.get(policy_id)
        result = self._simulation_engine.simulate(policy, context)
        self._events.append(
            PolicySimulated(
                policy_id=policy_id,
                policy_name=policy.name,
                action=result.action,
                would_execute=result.would_execute,
            )
        )
        return result

    def simulate_batch(
        self,
        policy_id: str,
        contexts: list[dict[str, Any]],
    ) -> list[SimulationResult]:
        policy = self._registry.get(policy_id)
        return self._simulation_engine.simulate_batch(policy, contexts)

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    def detect_conflicts(
        self,
        policy_id_a: str,
        policy_id_b: str,
    ) -> list[ConflictResult]:
        a = self._registry.get(policy_id_a)
        b = self._registry.get(policy_id_b)
        return self._conflict_detector.detect_policy_conflicts(a, b)

    def detect_internal_conflicts(self, policy_id: str) -> list[ConflictResult]:
        policy = self._registry.get(policy_id)
        return self._conflict_detector.detect_internal_conflicts(policy)

    # ------------------------------------------------------------------
    # Versioning
    # ------------------------------------------------------------------

    def get_versions(self, policy_id: str) -> list[Any]:
        return self._version_manager.get_versions(policy_id)

    def rollback(self, policy_id: str, target_version: str) -> AdvancedPolicyDefinition:
        restored = self._version_manager.rollback(policy_id, target_version)
        self._registry.update(restored)
        return restored

    # ------------------------------------------------------------------
    # DSL adapters
    # ------------------------------------------------------------------

    def import_from_dsl(
        self,
        raw: str,
        dsl_format: DSLFormat,
    ) -> AdvancedPolicyDefinition:
        """Import a policy from an external DSL format."""
        from q_guardian.policy.adapters import get_adapter

        adapter = get_adapter(dsl_format)
        result = adapter.to_policy(raw)
        if not result.success:
            from q_guardian.policy.exceptions import DSLAdapterError

            raise DSLAdapterError(f"Failed to import from {dsl_format.value}: {result.errors}")
        if result.policy:
            self.register_policy(result.policy)
            return result.policy
        raise PolicyEngineError("Import produced no policy")

    def export_to_dsl(
        self,
        policy_id: str,
        dsl_format: DSLFormat,
    ) -> DSLAdapterResult:
        """Export a policy to an external DSL format."""
        from q_guardian.policy.adapters import get_adapter

        policy = self._registry.get(policy_id)
        adapter = get_adapter(dsl_format)
        return adapter.from_policy(policy)

    # ------------------------------------------------------------------
    # RBAC
    # ------------------------------------------------------------------

    def init_rbac(self) -> None:
        from q_guardian.policy.rbac import RBACManager

        self._rbac = RBACManager(default_role=self._config.default_role)

    def check_permission(self, user_id: str, permission: Permission) -> bool:
        if self._rbac is None:
            return True
        return bool(self._rbac.check_permission(user_id, permission))

    @property
    def rbac(self) -> Any:
        return self._rbac

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def init_composition(self) -> None:
        from q_guardian.policy.composition import PolicyComposer

        self._composer = PolicyComposer(max_inheritance_depth=self._config.max_inheritance_depth)

    @property
    def composer(self) -> Any:
        return self._composer

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def parse_condition(expression: str) -> Condition | CompoundCondition:
        return parse_condition(expression)

    def get_events(self) -> list[Any]:
        return list(self._events)

    def clear_events(self) -> None:
        self._events.clear()

    @property
    def registry(self) -> PolicyRegistry:
        return self._registry

    @property
    def evaluator(self) -> PolicyEvaluator:
        return self._evaluator

    @property
    def version_manager(self) -> VersionManager:
        return self._version_manager

    @property
    def simulation_engine(self) -> SimulationEngine:
        return self._simulation_engine

    @property
    def conflict_detector(self) -> ConflictDetector:
        return self._conflict_detector

    @property
    def config(self) -> PolicyEngineConfig:
        return self._config
