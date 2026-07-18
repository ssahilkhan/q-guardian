"""Unit tests for framework state machine."""

from __future__ import annotations

import pytest

from q_guardian.core.framework_state import (
    FrameworkState,
    FrameworkStateMachine,
    StateTransitionError,
)


class TestFrameworkState:
    """Tests for FrameworkState enum."""

    def test_all_states_exist(self) -> None:
        """Verify all expected states are defined."""
        expected = {"initializing", "starting", "running", "stopping", "stopped", "error"}
        actual = {s.value for s in FrameworkState}
        assert actual == expected

    def test_state_string_values(self) -> None:
        """Verify state enum values are lowercase strings."""
        assert FrameworkState.INITIALIZING.value == "initializing"
        assert FrameworkState.RUNNING.value == "running"
        assert FrameworkState.STOPPED.value == "stopped"


class TestFrameworkStateMachine:
    """Tests for FrameworkStateMachine."""

    def test_initial_state(self) -> None:
        """Verify machine starts in INITIALIZING."""
        sm = FrameworkStateMachine()
        assert sm.state == FrameworkState.INITIALIZING

    def test_valid_transition(self) -> None:
        """Verify valid transition succeeds."""
        sm = FrameworkStateMachine()
        sm.transition_to(FrameworkState.STARTING)
        assert sm.state == FrameworkState.STARTING

    def test_full_lifecycle(self) -> None:
        """Verify complete lifecycle transitions."""
        sm = FrameworkStateMachine()
        sm.transition_to(FrameworkState.STARTING)
        sm.transition_to(FrameworkState.RUNNING)
        sm.transition_to(FrameworkState.STOPPING)
        sm.transition_to(FrameworkState.STOPPED)
        assert sm.state == FrameworkState.STOPPED

    def test_invalid_transition_raises(self) -> None:
        """Verify invalid transition raises StateTransitionError."""
        sm = FrameworkStateMachine()
        with pytest.raises(StateTransitionError):
            sm.transition_to(FrameworkState.RUNNING)

    def test_skip_same_state(self) -> None:
        """Verify transitioning to same state is a no-op."""
        sm = FrameworkStateMachine()
        sm.transition_to(FrameworkState.INITIALIZING)
        assert sm.state == FrameworkState.INITIALIZING

    def test_error_from_any_active_state(self) -> None:
        """Verify ERROR transition is valid from active states."""
        for state in [
            FrameworkState.INITIALIZING,
            FrameworkState.STARTING,
            FrameworkState.RUNNING,
            FrameworkState.STOPPING,
        ]:
            sm = FrameworkStateMachine()
            sm._state = state
            sm.transition_to(FrameworkState.ERROR)
            assert sm.state == FrameworkState.ERROR

    def test_is_running(self) -> None:
        """Verify is_running property."""
        sm = FrameworkStateMachine()
        assert sm.is_running is False
        sm._state = FrameworkState.RUNNING
        assert sm.is_running is True

    def test_is_stopped(self) -> None:
        """Verify is_stopped property."""
        sm = FrameworkStateMachine()
        assert sm.is_stopped is False
        sm._state = FrameworkState.STOPPED
        assert sm.is_stopped is True

    def test_is_error(self) -> None:
        """Verify is_error property."""
        sm = FrameworkStateMachine()
        assert sm.is_error is False
        sm._state = FrameworkState.ERROR
        assert sm.is_error is True

    def test_can_start(self) -> None:
        """Verify can_start property."""
        sm = FrameworkStateMachine()
        assert sm.can_start is True
        sm._state = FrameworkState.RUNNING
        assert sm.can_start is False

    def test_can_stop(self) -> None:
        """Verify can_stop property."""
        sm = FrameworkStateMachine()
        assert sm.can_stop is False
        sm._state = FrameworkState.RUNNING
        assert sm.can_stop is True


class TestStateTransitionError:
    """Tests for StateTransitionError."""

    def test_error_message(self) -> None:
        """Verify error message format."""
        exc = StateTransitionError(
            FrameworkState.RUNNING, FrameworkState.INITIALIZING
        )
        assert "running" in exc.message
        assert "initializing" in exc.message

    def test_error_details(self) -> None:
        """Verify error details include states."""
        exc = StateTransitionError(
            FrameworkState.RUNNING, FrameworkState.INITIALIZING
        )
        assert exc.details["current_state"] == "running"
        assert exc.details["target_state"] == "initializing"
        assert exc.code == "INVALID_STATE_TRANSITION"
