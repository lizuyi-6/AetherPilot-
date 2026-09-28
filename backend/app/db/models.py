"""SQLAlchemy models. State is persisted so experiments survive backend restarts."""

from __future__ import annotations

import time
import uuid

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class ExperimentRow(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _uid("exp"))
    name: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(40), default="CREATED")
    mode: Mapped[str] = mapped_column(String(20), default="demo")  # demo | real
    contract_json: Mapped[str] = mapped_column(Text, default="{}")
    config_json: Mapped[str] = mapped_column(Text, default="{}")       # current training config
    original_config_json: Mapped[str] = mapped_column(Text, default="{}")
    plan_json: Mapped[str] = mapped_column(Text, default="{}")
    workspace: Mapped[str] = mapped_column(String(500), default="")
    recovery_attempts: Mapped[int] = mapped_column(Integer, default=0)
    integrity_status: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    auto_changes: Mapped[int] = mapped_column(Integer, default=0)
    semantic_changes: Mapped[int] = mapped_column(Integer, default=0)
    best_checkpoint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    final_metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)
    completed_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class EventRow(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    ts: Mapped[float] = mapped_column(Float)
    experiment_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    severity: Mapped[str] = mapped_column(String(20), default="info")


class IncidentRow(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _uid("inc"))
    experiment_id: Mapped[str] = mapped_column(String(40), index=True)
    ts: Mapped[float] = mapped_column(Float, default=time.time)
    type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="OPEN")  # OPEN|RECOVERING|RESOLVED|FAILED
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    recovery_json: Mapped[str] = mapped_column(Text, default="{}")


class ApprovalRow(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: _uid("apr"))
    experiment_id: Mapped[str] = mapped_column(String(40), index=True)
    ts: Mapped[float] = mapped_column(Float, default=time.time)
    action_json: Mapped[str] = mapped_column(Text, default="{}")
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING|GRANTED|REJECTED
    resolved_at: Mapped[float | None] = mapped_column(Float, nullable=True)
