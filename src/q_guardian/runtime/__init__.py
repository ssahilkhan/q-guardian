"""Runtime abstraction layer for Q-Guardian.

This package defines the core domain models that represent an AI agent's
execution lifecycle. Every future module MUST use these runtime objects.

Modules:
    enums: Status and type enumerations
    models: Core domain models (Agent, AgentSession, etc.)
    context: RuntimeContext for plugin integration
    managers: SessionManager, RequestManager, trackers
"""

from __future__ import annotations

from q_guardian.runtime.context import RuntimeContext
from q_guardian.runtime.enums import (
    AgentStatus,
    MemoryOperation,
    MemoryType,
    RequestStatus,
    ResponseStatus,
    SessionStatus,
    ThreatSeverity,
    ThreatType,
    ToolType,
)
from q_guardian.runtime.managers import (
    MemoryTracker,
    RequestManager,
    SessionManager,
    ToolExecutionTracker,
)
from q_guardian.runtime.models import (
    Agent,
    AgentRequest,
    AgentResponse,
    AgentSession,
    MemoryAccess,
    RiskContext,
    SecurityContext,
    ThreatContext,
    TokenUsage,
    ToolInvocation,
)

__all__ = [
    # Models
    "Agent",
    "AgentRequest",
    "AgentResponse",
    "AgentSession",
    # Enums
    "AgentStatus",
    "MemoryAccess",
    "MemoryOperation",
    # Managers
    "MemoryTracker",
    "MemoryType",
    "RequestManager",
    "RequestStatus",
    "ResponseStatus",
    "RiskContext",
    # Context
    "RuntimeContext",
    "SecurityContext",
    "SessionManager",
    "SessionStatus",
    "ThreatContext",
    "ThreatSeverity",
    "ThreatType",
    "TokenUsage",
    "ToolExecutionTracker",
    "ToolInvocation",
    "ToolType",
]
