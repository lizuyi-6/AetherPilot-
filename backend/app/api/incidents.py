"""Incident + approval endpoints."""

from __future__ import annotations

import json
import time
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ..agent.orchestrator import get_orchestrator
from ..db.database import session_scope
from ..db.models import ApprovalRow
from ..incidents.manager import list_incidents

incidents_router = APIRouter(prefix="/api/experiments", tags=["incidents"])


@incidents_router.get("/{experiment_id}/incidents")
def get_incidents(experiment_id: str) -> list[dict]:
    return list_incidents(experiment_id)


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "reject"]


@incidents_router.post("/{experiment_id}/approval/{approval_id}")
def resolve_approval(experiment_id: str, approval_id: str, body: ApprovalDecision) -> dict[str, str]:
    with session_scope() as db:
        row = db.get(ApprovalRow, approval_id)
        if row is None or row.experiment_id != experiment_id:
            raise HTTPException(404, "approval not found")
        if row.status != "PENDING":
            raise HTTPException(409, f"approval already {row.status}")
        granted = body.decision == "approve"
        row.status = "GRANTED" if granted else "REJECTED"
        row.resolved_at = time.time()
    orch = get_orchestrator(experiment_id)
    if orch is not None:
        orch.resolve_approval(approval_id, granted)
    return {"status": "GRANTED" if granted else "REJECTED"}


@incidents_router.get("/{experiment_id}/approvals")
def list_approvals(experiment_id: str) -> list[dict]:
    with session_scope() as db:
        rows = db.scalars(
            select(ApprovalRow).where(ApprovalRow.experiment_id == experiment_id).order_by(ApprovalRow.ts)
        ).all()
        return [
            {"id": r.id, "ts": r.ts, "reason": r.reason, "status": r.status,
             "action": json.loads(r.action_json or "{}"), "resolved_at": r.resolved_at}
            for r in rows
        ]
