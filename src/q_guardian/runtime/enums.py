"""Enumerations for the Q-Guardian runtime abstraction layer.

Defines all status and type enumerations used across runtime models.
"""

from __future__ import annotations

from enum import StrEnum


class AgentStatus(StrEnum):
    """Lifecycle status of an AI agent."""

    INACTIVE = "inactive"
    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"


class SessionStatus(StrEnum):
    """Lifecycle status of an agent session."""

    OPEN = "open"
    CLOSED = "closed"
    EXPIRED = "expired"
    ERROR = "error"


class RequestStatus(StrEnum):
    """Status of an agent request."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ResponseStatus(StrEnum):
    """Status of an agent response."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"


class MemoryType(StrEnum):
    """Type of memory being accessed."""

    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    WORKING = "working"
    VECTOR = "vector"


class MemoryOperation(StrEnum):
    """Type of memory operation."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    SEARCH = "search"
    UPDATE = "update"


class ToolType(StrEnum):
    """Type of tool being invoked."""

    FUNCTION = "function"
    API = "api"
    DATABASE = "database"
    FILE = "file"
    SHELL = "shell"
    CUSTOM = "custom"


class ThreatSeverity(StrEnum):
    """Severity level of a detected threat."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ThreatType(StrEnum):
    """Category of detected threat."""

    PROMPT_INJECTION = "prompt_injection"
    JAILBREAK = "jailbreak"
    DATA_EXFILTRATION = "data_exfiltration"
    UNAUTHORIZED_TOOL_USE = "unauthorized_tool_use"
    ANOMALOUS_BEHAVIOR = "anomalous_behavior"
    POLICY_VIOLATION = "policy_violation"
    UNKNOWN = "unknown"
