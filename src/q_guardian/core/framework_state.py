"""Framework state machine for Q-Guardian.

Manages the lifecycle state of the framework, enforcing valid
state transitions and preventing illegal operations.
"""

from __future__ import annotations

from enum import Enum

import structlog

from q_guardian.exceptions.base import ApplicationException

logger = structlog.get_logger("framework.state")


class FrameworkState(str, Enum):
    """Enumeration of possible framework lifecycle states."""

    INITIALIZING = "initializing"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class StateTransitionError(ApplicationException):
    """Raised when an invalid state transition is attempted."""

    def __init__(
        self,
        current_state: FrameworkState,
        target_state: FrameworkState,
    ) -> None:
        message = (
            f"Cannot transition from '{current_state.value}' "
            f"to '{target_state.value}'"
        )
        super().__init__(
            message=message,
            code="INVALID_STATE_TRANSITION",
            status_code=500,
            details={
                "current_state": current_state.value,
                "target_state": target_state.value,
            },
        )


_VALID_TRANSITIONS: dict[FrameworkState, set[FrameworkState]] = {
    FrameworkState.INITIALIZING: {
        FrameworkState.STARTING,
        FrameworkState.ERROR,
        FrameworkState.STOPPED,
    },
    FrameworkState.STARTING: {
        FrameworkState.RUNNING,
        FrameworkState.ERROR,
        FrameworkState.STOPPING,
    },
    FrameworkState.RUNNING: {
        FrameworkState.STOPPING,
        FrameworkState.ERROR,
    },
    FrameworkState.STOPPING: {
        FrameworkState.STOPPED,
        FrameworkState.ERROR,
    },
    FrameworkState.STOPPED: set(),
    FrameworkState.ERROR: {
        FrameworkState.STOPPING,
        FrameworkState.INITIALIZING,
    },
}


class FrameworkStateMachine:
    """Manages framework lifecycle state transitions.

    Enforces a strict state machine where only valid transitions
    are allowed. Invalid transitions raise StateTransitionError.
    """

    def __init__(self) -> None:
        """Initialize the state machine in INITIALIZING state."""
        self._state: FrameworkState = FrameworkState.INITIALIZING

    @property
    def state(self) -> FrameworkState:
        """Return the current framework state."""
        return self._state

    def transition_to(self, new_state: FrameworkState) -> None:
        """Transition to a new state if the transition is valid.

        Args:
            new_state: The target state to transition to.

        Raises:
            StateTransitionError: If the transition is not valid.
        """
        if new_state == self._state:
            logger.debug(
                "state_transition_skipped",
                current=self._state.value,
                target=new_state.value,
                reason="already_in_state",
            )
            return

        allowed = _VALID_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            raise StateTransitionError(self._state, new_state)

        old_state = self._state
        self._state = new_state
        logger.info(
            "state_transition",
            from_state=old_state.value,
            to_state=new_state.value,
        )

    @property
    def is_running(self) -> bool:
        """Check if the framework is in RUNNING state."""
        return self._state == FrameworkState.RUNNING

    @property
    def is_stopped(self) -> bool:
        """Check if the framework is in STOPPED state."""
        return self._state == FrameworkState.STOPPED

    @property
    def is_error(self) -> bool:
        """Check if the framework is in ERROR state."""
        return self._state == FrameworkState.ERROR

    @property
    def can_start(self) -> bool:
        """Check if the framework can transition to STARTING."""
        return FrameworkState.STARTING in _VALID_TRANSITIONS.get(self._state, set())

    @property
    def can_stop(self) -> bool:
        """Check if the framework can transition to STOPPING."""
        return FrameworkState.STOPPING in _VALID_TRANSITIONS.get(self._state, set())
