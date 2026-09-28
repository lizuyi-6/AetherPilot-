"""Explicit experiment state machine. Transitions are validated and persisted."""

from __future__ import annotations

from enum import StrEnum


class ExperimentState(StrEnum):
    CREATED = "CREATED"
    CONTRACTING = "CONTRACTING"
    PREFLIGHT = "PREFLIGHT"
    PLANNING = "PLANNING"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    MONITORING = "MONITORING"
    INCIDENT = "INCIDENT"
    DIAGNOSING = "DIAGNOSING"
    RECOVERY_PLANNING = "RECOVERY_PLANNING"
    RECOVERING = "RECOVERING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EVALUATING = "EVALUATING"
    PACKAGING = "PACKAGING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = {
    ExperimentState.COMPLETED,
    ExperimentState.FAILED,
    ExperimentState.CANCELLED,
}

# Allowed transitions. Anything not listed raises InvalidTransition.
_TRANSITIONS: dict[ExperimentState, set[ExperimentState]] = {
    ExperimentState.CREATED: {ExperimentState.CONTRACTING, ExperimentState.CANCELLED},
    ExperimentState.CONTRACTING: {ExperimentState.PREFLIGHT, ExperimentState.FAILED, ExperimentState.CANCELLED},
    ExperimentState.PREFLIGHT: {ExperimentState.PLANNING, ExperimentState.FAILED, ExperimentState.CANCELLED},
    ExperimentState.PLANNING: {ExperimentState.PREPARING, ExperimentState.FAILED, ExperimentState.CANCELLED},
    ExperimentState.PREPARING: {ExperimentState.RUNNING, ExperimentState.FAILED, ExperimentState.CANCELLED},
    ExperimentState.RUNNING: {
        ExperimentState.MONITORING,
        ExperimentState.INCIDENT,
        ExperimentState.EVALUATING,
        ExperimentState.FAILED,
        ExperimentState.CANCELLED,
    },
    ExperimentState.MONITORING: {
        ExperimentState.INCIDENT,
        ExperimentState.EVALUATING,
        ExperimentState.FAILED,
        ExperimentState.CANCELLED,
    },
    ExperimentState.INCIDENT: {ExperimentState.DIAGNOSING, ExperimentState.FAILED, ExperimentState.CANCELLED},
    ExperimentState.DIAGNOSING: {
        ExperimentState.RECOVERY_PLANNING,
        ExperimentState.FAILED,
        ExperimentState.CANCELLED,
    },
    ExperimentState.RECOVERY_PLANNING: {
        ExperimentState.RECOVERING,
        ExperimentState.WAITING_APPROVAL,
        ExperimentState.FAILED,
        ExperimentState.CANCELLED,
    },
    ExperimentState.RECOVERING: {
        ExperimentState.RUNNING,
        ExperimentState.INCIDENT,
        ExperimentState.FAILED,
        ExperimentState.CANCELLED,
    },
    ExperimentState.WAITING_APPROVAL: {
        ExperimentState.RECOVERING,
        ExperimentState.FAILED,
        ExperimentState.CANCELLED,
    },
    ExperimentState.EVALUATING: {ExperimentState.PACKAGING, ExperimentState.FAILED},
    ExperimentState.PACKAGING: {ExperimentState.COMPLETED, ExperimentState.FAILED},
}


class InvalidTransition(ValueError):
    pass


class StateMachine:
    def __init__(self, initial: ExperimentState = ExperimentState.CREATED) -> None:
        self._state = initial

    @property
    def state(self) -> ExperimentState:
        return self._state

    def can_transition(self, target: ExperimentState) -> bool:
        return target in _TRANSITIONS.get(self._state, set())

    def transition(self, target: ExperimentState) -> ExperimentState:
        if not self.can_transition(target):
            raise InvalidTransition(f"{self._state} -> {target} not allowed")
        self._state = target
        return target

    def force(self, target: ExperimentState) -> ExperimentState:
        """Bypass transition rules — only for terminal failure handling when the
        experiment dies mid-state and the valid path to FAILED doesn't exist."""
        self._state = target
        return target
