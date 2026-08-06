"""Enumerations for the Risk & Decision Intelligence Engine.

Defines all domain enums used across the risk module. Enums are
isolated here to avoid circular imports and provide a single
source of truth for domain constants.
"""

from __future__ import annotations

from enum import StrEnum


class ThreatLevel(StrEnum):
    """Threat level classification."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskLevel(StrEnum):
    """Risk level classification."""

    MINIMAL = "minimal"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    SEVERE = "severe"
    CRITICAL = "critical"


class Severity(StrEnum):
    """Severity classification for threats."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TrustLevel(StrEnum):
    """Trust level for providers and predictions."""

    UNTRUSTED = "untrusted"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERIFIED = "verified"


class PolicyAction(StrEnum):
    """Actions that a policy can prescribe."""

    ALLOW = "allow"
    WARN = "warn"
    LOG = "log"
    REVIEW = "review"
    BLOCK = "block"
    QUARANTINE = "quarantine"
    TERMINATE_SESSION = "terminate_session"
    ESCALATE = "escalate"
    CUSTOM = "custom"


class PolicySeverity(StrEnum):
    """Severity classification for policies."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionOutcome(StrEnum):
    """Final decision outcome after policy evaluation."""

    ALLOWED = "allowed"
    WARNED = "warned"
    LOGGED = "logged"
    PENDING_REVIEW = "pending_review"
    BLOCKED = "blocked"
    QUARANTINED = "quarantined"
    SESSION_TERMINATED = "session_terminated"
    ESCALATED = "escalated"
    CUSTOM_ACTION = "custom_action"


class ActionType(StrEnum):
    """Types of actions the action engine can execute."""

    AUDIT_LOG = "audit_log"
    ALERT = "alert"
    EVENT = "event"
    BLOCK = "block"
    CONTINUE = "continue"
    NOTIFY_ADMIN = "notify_admin"
    WEBHOOK = "webhook"
    CUSTOM = "custom"


class AuditStatus(StrEnum):
    """Status of an audit record."""

    CREATED = "created"
    ACTIVE = "active"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
    ESCALATED = "escalated"


class ConfidenceMethod(StrEnum):
    """Confidence normalization methods."""

    NONE = "none"
    TEMPERATURE = "temperature"
    MIN_MAX = "min_max"
    Z_SCORE = "z_score"
    AGGREGATE = "aggregate"


class TrustAdjustmentReason(StrEnum):
    """Reasons for trust score adjustments."""

    CORRECT_PREDICTION = "correct_prediction"
    INCORRECT_PREDICTION = "incorrect_prediction"
    FALSE_POSITIVE = "false_positive"
    FALSE_NEGATIVE = "false_negative"
    TIMEOUT = "timeout"
    MANUAL_OVERRIDE = "manual_override"
    DECAY = "decay"
    BOOTSTRAP = "bootstrap"


class ExplanationFormat(StrEnum):
    """Output formats for explanations."""

    JSON = "json"
    TEXT = "text"
    MARKDOWN = "markdown"
    STRUCTURED = "structured"


class ReasoningNodeType(StrEnum):
    """Types of nodes in a reasoning graph."""

    INPUT = "input"
    PROCESS = "process"
    DECISION = "decision"
    EVIDENCE = "evidence"
    OUTCOME = "outcome"
    POLICY = "policy"
    ACTION = "action"
    RISK = "risk"
    TRUST = "trust"
    CONFIDENCE = "confidence"
