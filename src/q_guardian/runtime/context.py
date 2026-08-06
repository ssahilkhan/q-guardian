"""Runtime context for Q-Guardian.

Provides the RuntimeContext that is passed to all plugins during
execution, giving them access to the current agent, session, request,
and tracking data. Plugins MUST NOT directly manipulate session objects —
everything should pass through RuntimeContext.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.runtime.models import (
    Agent,
    AgentRequest,
    AgentResponse,
    AgentSession,
    MemoryAccess,
    SecurityContext,
    ThreatContext,
    ToolInvocation,
)


class RuntimeContext(BaseModel):
    """Shared object available during agent execution.

    Provides a single source of truth for the current execution state.
    All plugins receive this context and use it to:
    - Access the current agent, session, and request
    - Read/write security and threat information
    - Track tool invocations and memory accesses
    - Access the underlying FrameworkContext

    Plugins MUST NOT directly manipulate session objects. Everything
    should pass through RuntimeContext.

    Attributes:
        current_agent: The active AI agent.
        current_session: The active execution session.
        current_request: The current incoming request.
        current_response: The current outgoing response (if any).
        tool_invocations: List of tool calls in this execution.
        memory_accesses: List of memory operations in this execution.
        security: Runtime security state.
        threats: Detected threats (populated by threat detection plugins).
        framework_context: Reference to the underlying FrameworkContext.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
    )

    current_agent: Agent | None = Field(default=None, description="Active AI agent")
    current_session: AgentSession | None = Field(default=None, description="Active session")
    current_request: AgentRequest | None = Field(default=None, description="Current request")
    current_response: AgentResponse | None = Field(default=None, description="Current response")
    tool_invocations: list[ToolInvocation] = Field(
        default_factory=list, description="Tool invocations in this execution"
    )
    memory_accesses: list[MemoryAccess] = Field(
        default_factory=list, description="Memory accesses in this execution"
    )
    security: SecurityContext = Field(
        default_factory=SecurityContext, description="Runtime security state"
    )
    threats: list[ThreatContext] = Field(default_factory=list, description="Detected threats")
    risk: Any = Field(default=None, description="Risk context (populated by risk plugins)")
    framework_context: Any = Field(default=None, description="Underlying FrameworkContext")
    extra: dict[str, Any] = Field(default_factory=dict, description="Additional context data")

    # -- Agent shortcuts --

    @property
    def agent_id(self) -> str:
        """Return the current agent ID, or empty string if no agent."""
        return self.current_agent.id if self.current_agent else ""

    @property
    def agent_name(self) -> str:
        """Return the current agent name, or empty string if no agent."""
        return self.current_agent.name if self.current_agent else ""

    # -- Session shortcuts --

    @property
    def session_id(self) -> str:
        """Return the current session ID, or empty string if no session."""
        return self.current_session.session_id if self.current_session else ""

    # -- Request shortcuts --

    @property
    def prompt(self) -> str:
        """Return the current prompt text, or empty string if no request."""
        return self.current_request.prompt if self.current_request else ""

    # -- Blocking --

    @property
    def is_blocked(self) -> bool:
        """Check if execution is currently blocked."""
        return self.security.blocked

    # -- Tool tracking --

    def add_tool_invocation(self, invocation: ToolInvocation) -> None:
        """Record a tool invocation.

        Args:
            invocation: The tool invocation to record.
        """
        self.tool_invocations.append(invocation)

    @property
    def tool_count(self) -> int:
        """Return the number of tool invocations."""
        return len(self.tool_invocations)

    @property
    def failed_tool_count(self) -> int:
        """Return the number of failed tool invocations."""
        return sum(1 for t in self.tool_invocations if not t.success)

    # -- Memory tracking --

    def add_memory_access(self, access: MemoryAccess) -> None:
        """Record a memory access.

        Args:
            access: The memory access to record.
        """
        self.memory_accesses.append(access)

    @property
    def memory_access_count(self) -> int:
        """Return the number of memory accesses."""
        return len(self.memory_accesses)

    # -- Threat tracking --

    def add_threat(self, threat: ThreatContext) -> None:
        """Record a detected threat.

        Args:
            threat: The threat context to record.
        """
        self.threats.append(threat)

    @property
    def threat_count(self) -> int:
        """Return the number of detected threats."""
        return len(self.threats)

    def has_threats(self) -> bool:
        """Check if any threats have been detected."""
        return len(self.threats) > 0

    # -- Serialization --

    def to_snapshot(self) -> dict[str, Any]:
        """Create a point-in-time snapshot of the runtime context.

        Returns:
            Dictionary representation of the current context state.
        """
        return {
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "prompt": self.prompt[:200] if self.prompt else "",
            "tool_count": self.tool_count,
            "failed_tool_count": self.failed_tool_count,
            "memory_access_count": self.memory_access_count,
            "threat_count": self.threat_count,
            "is_blocked": self.is_blocked,
            "trust_score": self.security.trust_score,
            "risk_score": self.security.risk_score,
        }
