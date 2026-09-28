"""Incident persistence: SQLite + per-experiment JSON files in the workspace."""

from __future__ import annotations

import json
from pathlib import Path

from ..db.database import session_scope
from ..db.models import IncidentRow
from .models import Incident


def persist_incident(incident: Incident, workspace: Path) -> None:
    with session_scope() as db:
        db.add(
            IncidentRow(
                id=incident.id,
                experiment_id=incident.experiment_id,
                ts=incident.ts,
                type=incident.type.value,
                severity=incident.severity.value,
                status=incident.status.value,
                payload_json=incident.model_dump_json(),
            )
        )
    incidents_dir = workspace / "incidents"
    incidents_dir.mkdir(parents=True, exist_ok=True)
    (incidents_dir / f"{incident.id}.json").write_text(
        json.dumps(json.loads(incident.model_dump_json()), indent=2), encoding="utf-8"
    )


def update_incident_status(incident_id: str, status: str, recovery: dict | None = None) -> None:
    with session_scope() as db:
        row = db.get(IncidentRow, incident_id)
        if row is None:
            return
        row.status = status
        if recovery is not None:
            row.recovery_json = json.dumps(recovery)


def list_incidents(experiment_id: str) -> list[dict]:
    from sqlalchemy import select

    with session_scope() as db:
        rows = db.scalars(
            select(IncidentRow).where(IncidentRow.experiment_id == experiment_id).order_by(IncidentRow.ts)
        ).all()
        return [
            {
                "id": r.id,
                "ts": r.ts,
                "type": r.type,
                "severity": r.severity,
                "status": r.status,
                **json.loads(r.payload_json),
                "recovery": json.loads(r.recovery_json or "{}"),
            }
            for r in rows
        ]
