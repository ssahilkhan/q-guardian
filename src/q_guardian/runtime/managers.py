"""Runtime managers and trackers for Q-Guardian.

Provides SessionManager, RequestManager, ToolExecutionTracker, and
MemoryTracker. These classes manage the lifecycle and history of
runtime objects without containing business logic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from q_guardian.runtime.enums import MemoryOperation, MemoryType, SessionStatus
from q_guardian.runtime.models import (
    AgentRequest,
    AgentResponse,
    AgentSession,
    MemoryAccess,
    ToolInvocation,
)
from q_guardian.utils.uuid_utils import generate_uuid

logger = structlog.get_logger("runtime.managers")


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------


class SessionManager:
    """Manages agent session lifecycle.

    Responsibilities:
    - create_session()
    - get_session()
    - update_session()
    - close_session()
    - remove_expired_sessions()
    - list_active_sessions()

    All operations are async-compatible for framework integration.
    """

    def __init__(self, session_timeout_seconds: int = 3600) -> None:
        """Initialize the session manager.

        Args:
            session_timeout_seconds: Default session timeout in seconds.
        """
        self._sessions: dict[str, AgentSession] = {}
        self._session_timeout = timedelta(seconds=session_timeout_seconds)

    async def create_session(
        self,
        agent_id: str,
        conversation_id: str = "",
        user_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> AgentSession:
        """Create a new session.

        Args:
            agent_id: The agent that owns this session.
            conversation_id: Optional parent conversation ID.
            user_id: Optional end-user identifier.
            metadata: Optional session metadata.

        Returns:
            The newly created session.
        """
        session = AgentSession(
            agent_id=agent_id,
            conversation_id=conversation_id,
            user_id=user_id,
            metadata=metadata or {},
        )
        session.open()
        self._sessions[session.session_id] = session
        logger.info(
            "session_created",
            session_id=session.session_id,
            agent_id=agent_id,
        )
        return session

    async def get_session(self, session_id: str) -> AgentSession | None:
        """Retrieve a session by ID.

        Args:
            session_id: The session identifier.

        Returns:
            The session if found, None otherwise.
        """
        return self._sessions.get(session_id)

    async def update_session(
        self,
        session_id: str,
        **kwargs: Any,
    ) -> AgentSession | None:
        """Update session fields.

        Args:
            session_id: The session identifier.
            **kwargs: Fields to update on the session.

        Returns:
            The updated session if found, None otherwise.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None

        for key, value in kwargs.items():
            if hasattr(session, key):
                setattr(session, key, value)

        session.updated_at = datetime.now(UTC)
        return session

    async def close_session(self, session_id: str) -> bool:
        """Close a session.

        Args:
            session_id: The session identifier.

        Returns:
            True if the session was found and closed, False otherwise.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return False

        session.close()
        logger.info("session_closed", session_id=session_id)
        return True

    async def remove_expired_sessions(self) -> list[str]:
        """Remove sessions that have exceeded the timeout.

        Returns:
            List of removed session IDs.
        """
        now = datetime.now(UTC)
        expired = [
            sid
            for sid, session in self._sessions.items()
            if session.status == SessionStatus.OPEN
            and (now - session.updated_at) > self._session_timeout
        ]
        for sid in expired:
            self._sessions[sid].status = SessionStatus.EXPIRED
            del self._sessions[sid]
            logger.info("session_expired", session_id=sid)
        return expired

    async def list_active_sessions(self) -> list[AgentSession]:
        """List all open sessions.

        Returns:
            List of active sessions.
        """
        return [
            s for s in self._sessions.values()
            if s.status == SessionStatus.OPEN
        ]

    @property
    def session_count(self) -> int:
        """Return the total number of tracked sessions."""
        return len(self._sessions)

    async def clear(self) -> None:
        """Remove all sessions."""
        self._sessions.clear()


# ---------------------------------------------------------------------------
# RequestManager
# ---------------------------------------------------------------------------


class RequestManager:
    """Tracks incoming requests and their lifecycle.

    Tracks:
    - incoming requests
    - completed requests
    - failed requests
    - request history
    """

    def __init__(self, max_history: int = 1000) -> None:
        """Initialize the request manager.

        Args:
            max_history: Maximum number of requests to keep in history.
        """
        self._requests: dict[str, AgentRequest] = {}
        self._completed: dict[str, AgentResponse] = {}
        self._failed: list[str] = []
        self._history: list[str] = []
        self._max_history = max_history

    async def track_request(self, request: AgentRequest) -> None:
        """Track an incoming request.

        Args:
            request: The request to track.
        """
        self._requests[request.request_id] = request
        self._history.append(request.request_id)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        logger.info("request_tracked", request_id=request.request_id)

    async def complete_request(
        self,
        request_id: str,
        response: AgentResponse,
    ) -> None:
        """Mark a request as completed with its response.

        Args:
            request_id: The request identifier.
            response: The response for this request.
        """
        self._completed[request_id] = response
        self._requests.pop(request_id, None)
        logger.info("request_completed", request_id=request_id)

    async def fail_request(self, request_id: str, error: str = "") -> None:
        """Mark a request as failed.

        Args:
            request_id: The request identifier.
            error: Optional error description.
        """
        self._failed.append(request_id)
        self._requests.pop(request_id, None)
        logger.info("request_failed", request_id=request_id, error=error)

    async def get_request(self, request_id: str) -> AgentRequest | None:
        """Get a pending request by ID.

        Args:
            request_id: The request identifier.

        Returns:
            The request if found and still pending, None otherwise.
        """
        return self._requests.get(request_id)

    async def get_response(self, request_id: str) -> AgentResponse | None:
        """Get the response for a completed request.

        Args:
            request_id: The request identifier.

        Returns:
            The response if the request was completed, None otherwise.
        """
        return self._completed.get(request_id)

    async def get_history(self, limit: int = 50) -> list[str]:
        """Get recent request IDs.

        Args:
            limit: Maximum number of request IDs to return.

        Returns:
            List of recent request IDs (newest last).
        """
        return self._history[-limit:]

    @property
    def pending_count(self) -> int:
        """Return the number of pending requests."""
        return len(self._requests)

    @property
    def completed_count(self) -> int:
        """Return the number of completed requests."""
        return len(self._completed)

    @property
    def failed_count(self) -> int:
        """Return the number of failed requests."""
        return len(self._failed)

    @property
    def total_tracked(self) -> int:
        """Return total requests tracked (completed + failed + pending)."""
        return self.completed_count + self.failed_count + self.pending_count

    async def clear(self) -> None:
        """Clear all tracked data."""
        self._requests.clear()
        self._completed.clear()
        self._failed.clear()
        self._history.clear()


# ---------------------------------------------------------------------------
# ToolExecutionTracker
# ---------------------------------------------------------------------------


class ToolExecutionTracker:
    """Tracks tool execution lifecycle and history.

    Capabilities:
    - start invocation
    - finish invocation
    - execution history
    - execution statistics
    """

    def __init__(self, max_history: int = 500) -> None:
        """Initialize the tool execution tracker.

        Args:
            max_history: Maximum number of invocations to keep in history.
        """
        self._active: dict[str, ToolInvocation] = {}
        self._history: list[ToolInvocation] = []
        self._max_history = max_history

    def start_invocation(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolInvocation:
        """Start tracking a tool invocation.

        Args:
            tool_name: Name of the tool being invoked.
            arguments: Tool arguments.
            **kwargs: Additional fields for the invocation.

        Returns:
            The created ToolInvocation with a unique ID.
        """
        invocation = ToolInvocation(
            tool_name=tool_name,
            arguments=arguments or {},
            **kwargs,
        )
        self._active[invocation.invocation_id] = invocation
        return invocation

    def finish_invocation(
        self,
        invocation_id: str,
        result: Any = None,
        success: bool = True,
        error: str | None = None,
    ) -> ToolInvocation | None:
        """Finish tracking a tool invocation.

        Args:
            invocation_id: The invocation identifier.
            result: The tool execution result.
            success: Whether execution succeeded.
            error: Error message if failed.

        Returns:
            The completed invocation if found, None otherwise.
        """
        invocation = self._active.pop(invocation_id, None)
        if invocation is None:
            return None

        invocation.completed_at = datetime.now(UTC)
        invocation.duration = (
            invocation.completed_at - invocation.started_at
        ).total_seconds()
        invocation.result = result
        invocation.success = success
        invocation.error = error

        self._history.append(invocation)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        return invocation

    def get_invocation(self, invocation_id: str) -> ToolInvocation | None:
        """Get an active invocation by ID.

        Args:
            invocation_id: The invocation identifier.

        Returns:
            The invocation if still active, None otherwise.
        """
        return self._active.get(invocation_id)

    async def get_history(self, limit: int = 50) -> list[ToolInvocation]:
        """Get recent tool invocations.

        Args:
            limit: Maximum number of invocations to return.

        Returns:
            List of recent invocations (newest last).
        """
        return self._history[-limit:]

    def get_statistics(self) -> dict[str, Any]:
        """Get execution statistics.

        Returns:
            Dictionary with total, successful, and failed counts.
        """
        total = len(self._history)
        successful = sum(1 for i in self._history if i.success)
        failed = total - successful
        avg_duration = (
            sum(i.duration for i in self._history) / total
            if total > 0
            else 0.0
        )
        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "active": len(self._active),
            "average_duration": avg_duration,
        }

    @property
    def active_count(self) -> int:
        """Return the number of active invocations."""
        return len(self._active)

    @property
    def history_count(self) -> int:
        """Return the number of completed invocations."""
        return len(self._history)

    async def clear(self) -> None:
        """Clear all tracking data."""
        self._active.clear()
        self._history.clear()


# ---------------------------------------------------------------------------
# MemoryTracker
# ---------------------------------------------------------------------------


class MemoryTracker:
    """Tracks memory operations for audit and analysis.

    Track:
    - reads
    - writes
    - deletes
    - searches
    """

    def __init__(self, max_history: int = 1000) -> None:
        """Initialize the memory tracker.

        Args:
            max_history: Maximum number of accesses to keep in history.
        """
        self._history: list[MemoryAccess] = []
        self._max_history = max_history
        self._operation_counts: dict[MemoryOperation, int] = {
            op: 0 for op in MemoryOperation
        }

    def record_access(
        self,
        memory_type: MemoryType,
        operation: MemoryOperation,
        key: str,
        value: Any = None,
        agent_id: str = "",
        session_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> MemoryAccess:
        """Record a memory access.

        Args:
            memory_type: Type of memory being accessed.
            operation: Type of operation.
            key: Memory key or identifier.
            value: Value being read/written (optional).
            agent_id: Agent performing the access.
            session_id: Session context.
            metadata: Additional metadata.

        Returns:
            The created MemoryAccess record.
        """
        access = MemoryAccess(
            memory_type=memory_type,
            operation=operation,
            key=key,
            value=value,
            agent_id=agent_id,
            session_id=session_id,
            metadata=metadata or {},
        )
        self._history.append(access)
        self._operation_counts[operation] = (
            self._operation_counts.get(operation, 0) + 1
        )
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        return access

    def record_read(
        self,
        memory_type: MemoryType,
        key: str,
        value: Any = None,
        **kwargs: Any,
    ) -> MemoryAccess:
        """Convenience method to record a read operation.

        Args:
            memory_type: Type of memory being read.
            key: Memory key.
            value: Value that was read.
            **kwargs: Additional fields.

        Returns:
            The created MemoryAccess record.
        """
        return self.record_access(
            memory_type=memory_type,
            operation=MemoryOperation.READ,
            key=key,
            value=value,
            **kwargs,
        )

    def record_write(
        self,
        memory_type: MemoryType,
        key: str,
        value: Any = None,
        **kwargs: Any,
    ) -> MemoryAccess:
        """Convenience method to record a write operation.

        Args:
            memory_type: Type of memory being written.
            key: Memory key.
            value: Value being written.
            **kwargs: Additional fields.

        Returns:
            The created MemoryAccess record.
        """
        return self.record_access(
            memory_type=memory_type,
            operation=MemoryOperation.WRITE,
            key=key,
            value=value,
            **kwargs,
        )

    def record_delete(
        self,
        memory_type: MemoryType,
        key: str,
        **kwargs: Any,
    ) -> MemoryAccess:
        """Convenience method to record a delete operation.

        Args:
            memory_type: Type of memory being deleted.
            key: Memory key.
            **kwargs: Additional fields.

        Returns:
            The created MemoryAccess record.
        """
        return self.record_access(
            memory_type=memory_type,
            operation=MemoryOperation.DELETE,
            key=key,
            **kwargs,
        )

    def record_search(
        self,
        memory_type: MemoryType,
        key: str,
        value: Any = None,
        **kwargs: Any,
    ) -> MemoryAccess:
        """Convenience method to record a search operation.

        Args:
            memory_type: Type of memory being searched.
            key: Search query.
            value: Search results.
            **kwargs: Additional fields.

        Returns:
            The created MemoryAccess record.
        """
        return self.record_access(
            memory_type=memory_type,
            operation=MemoryOperation.SEARCH,
            key=key,
            value=value,
            **kwargs,
        )

    async def get_history(self, limit: int = 50) -> list[MemoryAccess]:
        """Get recent memory accesses.

        Args:
            limit: Maximum number of accesses to return.

        Returns:
            List of recent accesses (newest last).
        """
        return self._history[-limit:]

    def get_statistics(self) -> dict[str, Any]:
        """Get memory operation statistics.

        Returns:
            Dictionary with operation counts.
        """
        total = len(self._history)
        return {
            "total": total,
            "reads": self._operation_counts.get(MemoryOperation.READ, 0),
            "writes": self._operation_counts.get(MemoryOperation.WRITE, 0),
            "deletes": self._operation_counts.get(MemoryOperation.DELETE, 0),
            "searches": self._operation_counts.get(MemoryOperation.SEARCH, 0),
        }

    @property
    def total_accesses(self) -> int:
        """Return the total number of recorded accesses."""
        return len(self._history)

    async def clear(self) -> None:
        """Clear all tracking data."""
        self._history.clear()
        self._operation_counts = {op: 0 for op in MemoryOperation}
