"""Runtime domain models for Q-Guardian.

Defines the core domain objects that represent an AI agent's execution
lifecycle. Every future module (Prompt Security, Runtime Monitoring,
Threat Detection, Policy Engine, Quantum Engine, Dashboard) MUST use
these runtime objects.

These models contain NO threat detection logic, NO ML, NO quantum
algorithms — only reusable runtime abstractions.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from q_guardian.runtime.enums import (
    AgentStatus,
    MemoryOperation,
    MemoryType,
    SessionStatus,
    ThreatSeverity,
    ThreatType,
    ToolType,
)
from q_guardian.utils.uuid_utils import generate_uuid


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class Agent(BaseModel):
    """Represents an AI agent.

    An Agent is the primary entity in the runtime abstraction layer.
    It models an AI agent's identity, capabilities, and lifecycle state.

    Future modules use Agent to:
    - Track which agent is performing actions
    - Filter monitoring by agent capabilities
    - Apply policies per agent
    - Correlate threats to specific agents
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=generate_uuid, description="Unique agent identifier")
    name: str = Field(description="Human-readable agent name")
    framework: str = Field(default="unknown", description="AI framework (e.g. langgraph, crewai)")
    version: str = Field(default="1.0.0", description="Agent version string")
    capabilities: list[str] = Field(default_factory=list, description="Agent capabilities")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional agent metadata")
    status: AgentStatus = Field(default=AgentStatus.INACTIVE, description="Agent lifecycle status")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Creation timestamp")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Last update timestamp")

    def activate(self) -> None:
        """Transition agent to ACTIVE status."""
        self.status = AgentStatus.ACTIVE
        self.updated_at = datetime.now(UTC)

    def deactivate(self) -> None:
        """Transition agent to INACTIVE status."""
        self.status = AgentStatus.INACTIVE
        self.updated_at = datetime.now(UTC)

    def heartbeat(self) -> datetime:
        """Update the last-seen timestamp and return it.

        Returns:
            The updated timestamp.
        """
        self.updated_at = datetime.now(UTC)
        return self.updated_at


# ---------------------------------------------------------------------------
# AgentSession
# ---------------------------------------------------------------------------


class AgentSession(BaseModel):
    """Represents one execution session for an agent.

    A session groups a sequence of requests and responses within a
    bounded timeframe. Sessions are used for:
    - Request/response correlation
    - Duration tracking
    - Per-session security analysis
    - Resource lifecycle management
    """

    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(default_factory=generate_uuid, description="Unique session identifier")
    conversation_id: str = Field(default="", description="Parent conversation identifier")
    agent_id: str = Field(description="Agent that owns this session")
    user_id: str = Field(default="", description="End-user identifier")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Session creation time")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Last activity time")
    status: SessionStatus = Field(default=SessionStatus.OPEN, description="Session lifecycle status")
    request_count: int = Field(default=0, description="Number of requests in session")
    response_count: int = Field(default=0, description="Number of responses in session")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional session metadata")

    def open(self) -> None:
        """Transition session to OPEN status."""
        self.status = SessionStatus.OPEN
        self.created_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def close(self) -> None:
        """Transition session to CLOSED status."""
        self.status = SessionStatus.CLOSED
        self.updated_at = datetime.now(UTC)

    def reset(self) -> None:
        """Reset session counters and status to initial state."""
        self.request_count = 0
        self.response_count = 0
        self.status = SessionStatus.OPEN
        self.updated_at = datetime.now(UTC)

    def duration(self) -> float:
        """Calculate session duration in seconds.

        Returns:
            Duration from creation to last update (or now) in seconds.
        """
        end_time = self.updated_at
        if self.status == SessionStatus.OPEN:
            end_time = datetime.now(UTC)
        delta = end_time - self.created_at
        return delta.total_seconds()

    def increment_requests(self) -> int:
        """Increment request counter and return new count.

        Returns:
            Updated request count.
        """
        self.request_count += 1
        self.updated_at = datetime.now(UTC)
        return self.request_count

    def increment_responses(self) -> int:
        """Increment response counter and return new count.

        Returns:
            Updated response count.
        """
        self.response_count += 1
        self.updated_at = datetime.now(UTC)
        return self.response_count


# ---------------------------------------------------------------------------
# AgentRequest
# ---------------------------------------------------------------------------


class AgentRequest(BaseModel):
    """Represents one incoming request to an agent.

    Captures the full context of a request including the prompt,
    source information, and any attachments. Used by:
    - Prompt Security module for injection detection
    - Runtime Monitoring for request tracking
    - Policy Engine for request filtering
    """

    model_config = ConfigDict(populate_by_name=True)

    request_id: str = Field(default_factory=generate_uuid, description="Unique request identifier")
    session_id: str = Field(default="", description="Session this request belongs to")
    agent_id: str = Field(default="", description="Target agent identifier")
    prompt: str = Field(description="The prompt text")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Request timestamp")
    source: str = Field(default="unknown", description="Request origin (api, user, system)")
    attachments: list[dict[str, Any]] = Field(default_factory=list, description="Attached files or data")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional request metadata")


# ---------------------------------------------------------------------------
# TokenUsage
# ---------------------------------------------------------------------------


class TokenUsage(BaseModel):
    """Token usage statistics for a response."""

    model_config = ConfigDict(populate_by_name=True)

    prompt_tokens: int = Field(default=0, description="Tokens in prompt")
    completion_tokens: int = Field(default=0, description="Tokens in completion")
    total_tokens: int = Field(default=0, description="Total tokens used")


# ---------------------------------------------------------------------------
# AgentResponse
# ---------------------------------------------------------------------------


class AgentResponse(BaseModel):
    """Represents one response from an agent.

    Captures the agent's output along with performance metrics.
    Used by:
    - Dashboard for metrics display
    - Runtime Monitoring for response quality
    - Policy Engine for output filtering
    """

    model_config = ConfigDict(populate_by_name=True)

    response_id: str = Field(default_factory=generate_uuid, description="Unique response identifier")
    request_id: str = Field(default="", description="Corresponding request identifier")
    session_id: str = Field(default="", description="Session this response belongs to")
    output: str = Field(default="", description="Agent output text")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Response timestamp")
    execution_time: float = Field(default=0.0, description="Execution time in seconds")
    token_usage: TokenUsage = Field(default_factory=TokenUsage, description="Token usage statistics")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional response metadata")


# ---------------------------------------------------------------------------
# ToolInvocation
# ---------------------------------------------------------------------------


class ToolInvocation(BaseModel):
    """Represents one tool execution.

    Tracks the full lifecycle of a tool call including arguments,
    results, and timing. Used by:
    - Runtime Monitoring for tool usage analysis
    - Threat Detection for unauthorized tool use
    - Dashboard for tool usage metrics
    """

    model_config = ConfigDict(populate_by_name=True)

    invocation_id: str = Field(default_factory=generate_uuid, description="Unique invocation ID")
    tool_name: str = Field(description="Name of the tool")
    tool_type: ToolType = Field(default=ToolType.FUNCTION, description="Tool type category")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    result: Any = Field(default=None, description="Tool execution result")
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Start timestamp")
    completed_at: datetime | None = Field(default=None, description="Completion timestamp")
    duration: float = Field(default=0.0, description="Execution duration in seconds")
    success: bool = Field(default=True, description="Whether execution succeeded")
    error: str | None = Field(default=None, description="Error message if failed")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


# ---------------------------------------------------------------------------
# MemoryAccess
# ---------------------------------------------------------------------------


class MemoryAccess(BaseModel):
    """Represents interaction with agent memory.

    Tracks all memory operations for audit and security analysis.
    Used by:
    - Runtime Monitoring for memory usage patterns
    - Threat Detection for data exfiltration attempts
    - Dashboard for memory metrics
    """

    model_config = ConfigDict(populate_by_name=True)

    access_id: str = Field(default_factory=generate_uuid, description="Unique access ID")
    memory_type: MemoryType = Field(description="Type of memory")
    operation: MemoryOperation = Field(description="Type of operation")
    key: str = Field(description="Memory key or identifier")
    value: Any = Field(default=None, description="Value being read/written")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Operation timestamp")
    agent_id: str = Field(default="", description="Agent performing the access")
    session_id: str = Field(default="", description="Session context")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


# ---------------------------------------------------------------------------
# SecurityContext
# ---------------------------------------------------------------------------


class SecurityContext(BaseModel):
    """Contains runtime security information.

    Aggregates security state during an agent's execution. Updated
    continuously by security plugins as they analyze requests,
    responses, and tool calls.
    """

    model_config = ConfigDict(populate_by_name=True)

    trust_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Trust score 0-1")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Risk score 0-1")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Analysis confidence 0-1")
    active_policies: list[str] = Field(default_factory=list, description="Currently active policies")
    alerts: list[str] = Field(default_factory=list, description="Active security alerts")
    violations: list[str] = Field(default_factory=list, description="Policy violations detected")
    blocked: bool = Field(default=False, description="Whether execution is blocked")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional security metadata")

    def update_trust(self, score: float) -> None:
        """Update trust score with bounds checking.

        Args:
            score: New trust score between 0.0 and 1.0.
        """
        self.trust_score = max(0.0, min(1.0, score))

    def update_risk(self, score: float) -> None:
        """Update risk score with bounds checking.

        Args:
            score: New risk score between 0.0 and 1.0.
        """
        self.risk_score = max(0.0, min(1.0, score))

    def add_alert(self, alert: str) -> None:
        """Add a security alert.

        Args:
            alert: Alert message to add.
        """
        if alert not in self.alerts:
            self.alerts.append(alert)

    def add_violation(self, violation: str) -> None:
        """Record a policy violation.

        Args:
            violation: Violation description to add.
        """
        if violation not in self.violations:
            self.violations.append(violation)

    def block(self) -> None:
        """Block execution."""
        self.blocked = True

    def unblock(self) -> None:
        """Unblock execution."""
        self.blocked = False


# ---------------------------------------------------------------------------
# ThreatContext
# ---------------------------------------------------------------------------


class ThreatContext(BaseModel):
    """Represents a detected threat.

    Created by threat detection plugins when they identify a
    potential security threat. Contains all information needed
    for incident response and dashboard display.
    """

    model_config = ConfigDict(populate_by_name=True)

    threat_id: str = Field(default_factory=generate_uuid, description="Unique threat ID")
    threat_type: ThreatType = Field(default=ThreatType.UNKNOWN, description="Category of threat")
    severity: ThreatSeverity = Field(default=ThreatSeverity.LOW, description="Threat severity")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Detection confidence")
    indicators: list[str] = Field(default_factory=list, description="Indicators of compromise")
    evidence: dict[str, Any] = Field(default_factory=dict, description="Supporting evidence")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Detection timestamp")
    source: str = Field(default="unknown", description="Detection source")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


# ---------------------------------------------------------------------------
# RiskContext
# ---------------------------------------------------------------------------


class RiskContext(BaseModel):
    """Represents calculated risk for an operation.

    Created by risk calculation plugins. Provides structured
    risk assessment with factors and recommendations.
    """

    model_config = ConfigDict(populate_by_name=True)

    score: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall risk score 0-1")
    factors: list[str] = Field(default_factory=list, description="Contributing risk factors")
    explanation: str = Field(default="", description="Human-readable risk explanation")
    recommendation: str = Field(default="", description="Recommended action")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Calculation timestamp")
