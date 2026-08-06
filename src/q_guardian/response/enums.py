"""Enums for the Autonomous Response & Recovery Engine."""

from __future__ import annotations

from enum import StrEnum


class ResponseAction(StrEnum):
    """Actions the response engine can take."""

    ALLOW = "allow"
    BLOCK = "block"
    WARN = "warn"
    QUARANTINE = "quarantine"
    TERMINATE = "terminate"
    ESCALATE = "escalate"
    MONITOR = "monitor"
    MANUAL_APPROVAL = "manual_approval"
    DELAYED_ACTION = "delayed_action"
    RETRY = "retry"
    ROLLBACK = "rollback"
    LOG_ONLY = "log_only"
    NOTIFY = "notify"
    ISOLATE = "isolate"
    RESTORE = "restore"


class ResponseStatus(StrEnum):
    """Status of a response execution."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_APPROVAL = "waiting_approval"
    ROLLED_BACK = "rolled_back"
    TIMED_OUT = "timed_out"
    PARTIAL = "partial"


class StepStatus(StrEnum):
    """Status of an individual playbook step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING = "waiting"
    ROLLED_BACK = "rolled_back"
    TIMED_OUT = "timed_out"


class StepType(StrEnum):
    """Types of playbook steps."""

    ACTION = "action"
    CONDITION = "condition"
    PARALLEL = "parallel"
    APPROVAL = "approval"
    WAIT = "wait"
    ROLLBACK = "rollback"
    NOTIFICATION = "notification"
    EVIDENCE = "evidence"
    BRANCH = "branch"
    SUB_PLAYBOOK = "sub_playbook"


class QuarantineType(StrEnum):
    """Types of quarantine targets."""

    AGENT = "agent"
    SESSION = "session"
    PLUGIN = "plugin"
    MEMORY = "memory"
    TOOL = "tool"
    FULL = "full"


class QuarantineStatus(StrEnum):
    """Status of a quarantine."""

    ACTIVE = "active"
    EXPIRED = "expired"
    MANUALLY_RELEASED = "manually_released"
    AUTO_RELEASED = "auto_released"
    ESCALATED = "escalated"


class EvidenceType(StrEnum):
    """Types of evidence artifacts."""

    PROMPT = "prompt"
    RUNTIME_CONTEXT = "runtime_context"
    THREAT_PREDICTION = "threat_prediction"
    FUSION_OUTPUT = "fusion_output"
    RISK_ASSESSMENT = "risk_assessment"
    POLICY_DECISION = "policy_decision"
    ACTION_RESULT = "action_result"
    TIMELINE = "timeline"
    PLUGIN_STATE = "plugin_state"
    SYSTEM_STATE = "system_state"
    CUSTOM = "custom"


class NotificationChannel(StrEnum):
    """Notification delivery channels."""

    EMAIL = "email"
    WEBHOOK = "webhook"
    SLACK = "slack"
    TEAMS = "teams"
    PAGERDUTY = "pagerduty"
    DISCORD = "discord"
    LOG = "log"
    SMS = "sms"


class NotificationPriority(StrEnum):
    """Priority levels for notifications."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalType(StrEnum):
    """Types of approval workflows."""

    AUTOMATIC = "automatic"
    MANUAL = "manual"
    MULTI_LEVEL = "multi_level"
    TIMEOUT = "timeout"
    QUORUM = "quorum"


class ApprovalStatus(StrEnum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class IntegrationType(StrEnum):
    """SOAR integration types."""

    SENTINEL = "sentinel"
    SPLUNK = "splunk"
    QRADAR = "qradar"
    CORTEX_XSOAR = "cortex_xsoar"
    SERVICENOW = "servicenow"
    CUSTOM = "custom"


class RollbackTarget(StrEnum):
    """Targets that can be rolled back."""

    POLICY = "policy"
    SESSION = "session"
    PLUGIN = "plugin"
    CONFIGURATION = "configuration"
    RUNTIME = "runtime"
    FULL = "full"


class RecoveryAction(StrEnum):
    """Types of recovery actions."""

    RESUME_SESSION = "resume_session"
    RESTORE_RUNTIME = "restore_runtime"
    RESTORE_PLUGINS = "restore_plugins"
    RESTORE_MEMORY = "restore_memory"
    RETRY_REQUEST = "retry_request"
    RESTORE_POLICY = "restore_policy"
    RESTART_AGENT = "restart_agent"
    CUSTOM = "custom"


class TimelineFormat(StrEnum):
    """Output formats for timelines."""

    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"
    CSV = "csv"


class FailureStrategy(StrEnum):
    """How to handle step failures in playbooks."""

    STOP = "stop"
    CONTINUE = "continue"
    RETRY = "retry"
    ROLLBACK = "rollback"
    SKIP = "skip"
    ESCALATE = "escalate"
