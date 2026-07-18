"""Configuration for the Autonomous Response & Recovery Engine."""

from __future__ import annotations

from pydantic import BaseModel, Field

from q_guardian.response.enums import FailureStrategy, NotificationChannel


class ResponseEngineConfig(BaseModel):
    """Configuration for the response engine."""

    # Response
    default_timeout_seconds: float = 30.0
    max_concurrent_responses: int = 10
    enable_correlation_ids: bool = True
    enable_idempotency: bool = True
    default_failure_strategy: FailureStrategy = FailureStrategy.STOP

    # Playbooks
    playbook_directory: str = "playbooks/"
    enable_playbook_validation: bool = True
    max_playbook_steps: int = 100
    playbook_timeout_seconds: float = 300.0

    # Quarantine
    default_quarantine_duration_seconds: float = 3600.0
    max_quarantine_duration_seconds: float = 86400.0
    enable_auto_release: bool = True
    auto_release_check_interval_seconds: float = 60.0

    # Evidence
    enable_evidence_collection: bool = True
    evidence_immutable: bool = True
    evidence_storage_path: str = "evidence/"
    max_evidence_size_bytes: int = 10 * 1024 * 1024  # 10MB
    evidence_retention_days: int = 90

    # Timeline
    enable_timeline: bool = True
    timeline_formats: list[str] = Field(default_factory=lambda: ["json", "markdown"])

    # Notifications
    enabled_channels: list[NotificationChannel] = Field(
        default_factory=lambda: [NotificationChannel.LOG]
    )
    notification_timeout_seconds: float = 10.0
    max_notification_retries: int = 3

    # Approval
    approval_timeout_seconds: float = 300.0
    require_approval_for: list[str] = Field(
        default_factory=lambda: ["terminate", "rollback", "quarantine"]
    )

    # Recovery
    enable_auto_recovery: bool = True
    max_recovery_attempts: int = 3
    recovery_delay_seconds: float = 5.0

    # Rollback
    enable_checkpointing: bool = True
    max_checkpoints: int = 50

    # Integrations
    enabled_integrations: list[str] = Field(default_factory=list)

    # Storage
    persist_responses: bool = False
    storage_path: str = "response_store.json"

    # Logging
    log_responses: bool = True
    log_level: str = "INFO"
