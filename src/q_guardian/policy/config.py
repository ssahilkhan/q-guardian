"""Configuration for the Advanced Policy Engine."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from q_guardian.policy.enums import ConflictResolution, DSLFormat


class PolicyEngineConfig(BaseModel):
    """Configuration for the Advanced Policy Engine."""

    # Evaluation
    evaluation_timeout_seconds: float = 5.0
    max_rules_per_policy: int = 1000
    max_nested_depth: int = 10
    enable_async: bool = True

    # Conflict detection
    auto_detect_conflicts: bool = True
    default_conflict_resolution: ConflictResolution = ConflictResolution.PRIORITY
    allow_overlapping_rules: bool = True

    # Versioning
    enable_versioning: bool = True
    max_versions_per_policy: int = 50
    auto_snapshot_on_update: bool = True

    # Simulation
    enable_simulation: bool = True
    simulation_max_context_size: int = 10000

    # Persistence
    persist_to_file: bool = False
    storage_path: str = "policy_store.json"
    auto_save: bool = True

    # RBAC
    enable_rbac: bool = False
    default_role: str = "viewer"

    # DSL adapters
    enabled_adapters: list[DSLFormat] = Field(
        default_factory=lambda: [DSLFormat.YAML, DSLFormat.JSON]
    )
    custom_adapter_modules: list[str] = Field(default_factory=list)

    # Composition
    enable_composition: bool = True
    max_inheritance_depth: int = 5

    # Logging
    log_evaluations: bool = True
    log_level: str = "INFO"

    # Custom settings
    custom: dict[str, Any] = Field(default_factory=dict)
