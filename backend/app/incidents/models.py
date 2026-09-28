"""Incident data model."""

from __future__ import annotations

import time
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class IncidentType(StrEnum):
    CUDA_OOM = "CUDA_OOM"
    NAN_LOSS = "NAN_LOSS"
    PROCESS_CRASH = "PROCESS_CRASH"
    DISK_LOW = "DISK_LOW"
    GPU_UNAVAILABLE = "GPU_UNAVAILABLE"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    RECOVERING = "RECOVERING"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"


class Incident(BaseModel):
    id: str = Field(default_factory=lambda: f"inc-{uuid.uuid4().hex[:8]}")
    experiment_id: str
    type: IncidentType
    severity: Severity
    ts: float = Field(default_factory=time.time)
    evidence: list[str] = Field(default_factory=list)
    root_cause: str = ""
    confidence: float = 0.0
    recommended_actions: list[str] = Field(default_factory=list)
    status: IncidentStatus = IncidentStatus.OPEN
    extra: dict[str, Any] = Field(default_factory=dict)
