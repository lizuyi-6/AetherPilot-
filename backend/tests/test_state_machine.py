"""State machine transition tests."""

from __future__ import annotations

import pytest

from app.agent.state_machine import ExperimentState, InvalidTransition, StateMachine


def test_happy_path() -> None:
    sm = StateMachine()
    for target in (
        ExperimentState.CONTRACTING, ExperimentState.PREFLIGHT, ExperimentState.PLANNING,
        ExperimentState.PREPARING, ExperimentState.RUNNING, ExperimentState.MONITORING,
        ExperimentState.EVALUATING, ExperimentState.PACKAGING, ExperimentState.COMPLETED,
    ):
        sm.transition(target)
    assert sm.state is ExperimentState.COMPLETED


def test_incident_recovery_loop() -> None:
    sm = StateMachine()
    for target in (
        ExperimentState.CONTRACTING, ExperimentState.PREFLIGHT, ExperimentState.PLANNING,
        ExperimentState.PREPARING, ExperimentState.RUNNING, ExperimentState.MONITORING,
        ExperimentState.INCIDENT, ExperimentState.DIAGNOSING, ExperimentState.RECOVERY_PLANNING,
        ExperimentState.RECOVERING, ExperimentState.RUNNING,
    ):
        sm.transition(target)
    assert sm.state is ExperimentState.RUNNING


def test_approval_path() -> None:
    sm = StateMachine()
    for target in (
        ExperimentState.CONTRACTING, ExperimentState.PREFLIGHT, ExperimentState.PLANNING,
        ExperimentState.PREPARING, ExperimentState.RUNNING, ExperimentState.INCIDENT,
        ExperimentState.DIAGNOSING, ExperimentState.RECOVERY_PLANNING,
        ExperimentState.WAITING_APPROVAL, ExperimentState.RECOVERING, ExperimentState.RUNNING,
    ):
        sm.transition(target)
    assert sm.state is ExperimentState.RUNNING


def test_invalid_transition_raises() -> None:
    sm = StateMachine()
    with pytest.raises(InvalidTransition):
        sm.transition(ExperimentState.RUNNING)
    with pytest.raises(InvalidTransition):
        sm.transition(ExperimentState.COMPLETED)


def test_terminal_states_have_no_exits() -> None:
    for terminal in (ExperimentState.COMPLETED, ExperimentState.FAILED, ExperimentState.CANCELLED):
        sm = StateMachine(terminal)
        for target in ExperimentState:
            assert not sm.can_transition(target)
