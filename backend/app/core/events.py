"""Structured event system.

Every meaningful action in the system emits an Event. Events are:
  1. persisted (SQLite + timeline.jsonl in the experiment workspace),
  2. streamed to WebSocket subscribers in real time,
  3. used for audit, the UI timeline, and the final report.
"""

from __future__ import annotations

import asyncio
import itertools
import time
import uuid
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    # lifecycle
    EXPERIMENT_CREATED = "EXPERIMENT_CREATED"
    STATE_CHANGED = "STATE_CHANGED"
    # preflight
    SYSTEM_PREFLIGHT_STARTED = "SYSTEM_PREFLIGHT_STARTED"
    GPU_DETECTED = "GPU_DETECTED"
    GPU_UNAVAILABLE = "GPU_UNAVAILABLE"
    CUDA_CHECKED = "CUDA_CHECKED"
    DOCKER_CHECKED = "DOCKER_CHECKED"
    STORAGE_CHECKED = "STORAGE_CHECKED"
    ENVIRONMENT_RECORDED = "ENVIRONMENT_RECORDED"
    DATASET_HASHED = "DATASET_HASHED"
    MODEL_CHECKED = "MODEL_CHECKED"
    RESOURCE_ESTIMATED = "RESOURCE_ESTIMATED"
    PREFLIGHT_COMPLETED = "PREFLIGHT_COMPLETED"
    # planning
    CONTRACT_CREATED = "CONTRACT_CREATED"
    EXPERIMENT_PLAN_CREATED = "EXPERIMENT_PLAN_CREATED"
    CONFIG_GENERATED = "CONFIG_GENERATED"
    # execution
    TRAINING_STARTED = "TRAINING_STARTED"
    TRAINING_PROGRESS = "TRAINING_PROGRESS"
    CHECKPOINT_CREATED = "CHECKPOINT_CREATED"
    TELEMETRY_SAMPLE = "TELEMETRY_SAMPLE"
    # incidents / recovery
    INCIDENT_DETECTED = "INCIDENT_DETECTED"
    DIAGNOSIS_STARTED = "DIAGNOSIS_STARTED"
    DIAGNOSIS_COMPLETED = "DIAGNOSIS_COMPLETED"
    RECOVERY_PLAN_CREATED = "RECOVERY_PLAN_CREATED"
    INTEGRITY_CHECKED = "INTEGRITY_CHECKED"
    CONFIG_PATCH_APPLIED = "CONFIG_PATCH_APPLIED"
    CHECKPOINT_ROLLBACK = "CHECKPOINT_ROLLBACK"
    TRAINING_RESUMED = "TRAINING_RESUMED"
    RECOVERY_SUCCEEDED = "RECOVERY_SUCCEEDED"
    RECOVERY_FAILED = "RECOVERY_FAILED"
    # approvals
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    # completion
    EVALUATION_STARTED = "EVALUATION_STARTED"
    EVALUATION_COMPLETED = "EVALUATION_COMPLETED"
    EXPERIMENT_COMPLETED = "EXPERIMENT_COMPLETED"
    EXPERIMENT_FAILED = "EXPERIMENT_FAILED"
    EXPERIMENT_CANCELLED = "EXPERIMENT_CANCELLED"
    PACKAGE_CREATED = "PACKAGE_CREATED"
    AGENT_NOTE = "AGENT_NOTE"


class Event(BaseModel):
    id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    ts: float = Field(default_factory=time.time)
    experiment_id: str | None = None
    type: EventType
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    severity: str = "info"  # info | warning | error


PersistHook = Callable[[Event], Awaitable[None] | None]


class EventBus:
    """In-process async pub/sub. Subscribers filter by experiment_id (None = all)."""

    def __init__(self) -> None:
        self._subscribers: set[tuple[asyncio.Queue[Event], str | None]] = set()
        self._persist_hooks: list[PersistHook] = []
        self._counter = itertools.count(1)

    def add_persist_hook(self, hook: PersistHook) -> None:
        self._persist_hooks.append(hook)

    def subscribe(self, experiment_id: str | None = None, maxsize: int = 2000) -> asyncio.Queue[Event]:
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.add((q, experiment_id))
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        self._subscribers = {s for s in self._subscribers if s[0] is not q}

    async def emit(self, event: Event) -> Event:
        for hook in self._persist_hooks:
            result = hook(event)
            if asyncio.iscoroutine(result):
                await result
        for q, exp_filter in list(self._subscribers):
            if exp_filter is not None and exp_filter != event.experiment_id:
                continue
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Slow consumer: drop telemetry-class events rather than block the agent.
                if event.type not in (EventType.TELEMETRY_SAMPLE, EventType.TRAINING_PROGRESS):
                    try:
                        q.get_nowait()
                        q.put_nowait(event)
                    except asyncio.QueueEmpty:
                        pass
        return event


# Global bus used by the app. Tests can instantiate their own.
bus = EventBus()
