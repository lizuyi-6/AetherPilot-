"""Experiment CRUD + lifecycle endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..agent.orchestrator import get_orchestrator, start_orchestrator
from ..agent.reasoning import get_reasoner
from ..contracts.models import ExperimentContract
from ..contracts.validator import ContractError, validate_contract
from ..core.config import settings
from ..core.events import Event, EventType, bus
from ..db.database import session_scope
from ..db.models import EventRow, ExperimentRow

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


class CreateExperimentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, description="free-text experiment goal")
    mode: Literal["demo", "real"] = "demo"
    demo: dict[str, Any] = Field(default_factory=dict)
    contract_overrides: dict[str, Any] = Field(default_factory=dict)


def _row_to_summary(row: ExperimentRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "state": row.state,
        "mode": row.mode,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "completed_at": row.completed_at,
        "recovery_attempts": row.recovery_attempts,
        "integrity_status": row.integrity_status,
        "best_checkpoint": row.best_checkpoint,
        "error": row.error,
    }


def _build_contract(req: CreateExperimentRequest, parsed_goal: dict[str, Any]) -> ExperimentContract:
    contract_dict: dict[str, Any] = {
        "experiment": {"name": req.name},
        "goal": {
            "type": parsed_goal.get("type", "finetune"),
            "model": parsed_goal.get("model", "demo-small"),
            "dataset": parsed_goal.get("dataset", "demo://aether-v03"),
            "description": req.goal,
        },
        "constraints": {},
        "metrics": {},
    }
    if "max_vram_gb" in parsed_goal:
        contract_dict["constraints"]["max_vram_gb"] = parsed_goal["max_vram_gb"]
    if "max_duration_hours" in parsed_goal:
        contract_dict["constraints"]["max_duration_hours"] = parsed_goal["max_duration_hours"]
    if "metric" in parsed_goal:
        metric = parsed_goal["metric"]
        contract_dict["metrics"][metric["name"]] = {"target": metric["target"], "operator": metric["operator"]}
    # User overrides win over parsed values.
    overrides = req.contract_overrides
    for section in ("constraints", "permissions", "metrics", "recovery", "reproducibility", "goal"):
        if section in overrides:
            contract_dict.setdefault(section, {})
            if isinstance(contract_dict[section], dict) and isinstance(overrides[section], dict):
                contract_dict[section].update(overrides[section])
    return ExperimentContract.model_validate(contract_dict)


@router.post("")
async def create_experiment(req: CreateExperimentRequest) -> dict[str, Any]:
    reasoner = get_reasoner()
    parsed_goal = reasoner.parse_goal(req.goal)
    try:
        contract = _build_contract(req, parsed_goal)
        warnings = validate_contract(contract)
    except (ContractError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    experiment_id: str
    with session_scope() as db:
        row = ExperimentRow(
            name=req.name,
            mode=req.mode,
            contract_json=contract.model_dump_json(),
            config_json=json.dumps({"demo": req.demo}),
            plan_json=json.dumps({"parsed_goal": parsed_goal, "reasoner": reasoner.name}),
        )
        db.add(row)
        db.flush()
        experiment_id = row.id
        row.workspace = str(settings.experiments_dir / experiment_id)
    await bus.emit(Event(
        type=EventType.EXPERIMENT_CREATED, experiment_id=experiment_id,
        message=req.name, payload={"mode": req.mode, "goal": req.goal, "warnings": warnings},
    ))
    return {"id": experiment_id, "state": "CREATED", "contract": contract.model_dump(mode="json"),
            "parsed_goal": parsed_goal, "warnings": warnings}


@router.get("")
def list_experiments() -> list[dict[str, Any]]:
    with session_scope() as db:
        rows = db.scalars(select(ExperimentRow).order_by(ExperimentRow.created_at.desc())).all()
        return [_row_to_summary(r) for r in rows]


@router.get("/{experiment_id}")
def get_experiment(experiment_id: str) -> dict[str, Any]:
    with session_scope() as db:
        row = db.get(ExperimentRow, experiment_id)
        if row is None:
            raise HTTPException(404, "experiment not found")
        summary = _row_to_summary(row)
        summary.update({
            "contract": json.loads(row.contract_json),
            "config": json.loads(row.config_json or "{}"),
            "original_config": json.loads(row.original_config_json or "{}"),
            "final_metrics": json.loads(row.final_metrics_json or "{}"),
            "auto_changes": row.auto_changes,
            "semantic_changes": row.semantic_changes,
            "workspace": row.workspace,
        })
        return summary


@router.post("/{experiment_id}/start")
async def start_experiment(experiment_id: str) -> dict[str, str]:
    with session_scope() as db:
        row = db.get(ExperimentRow, experiment_id)
        if row is None:
            raise HTTPException(404, "experiment not found")
        if row.state != "CREATED":
            raise HTTPException(409, f"cannot start from state {row.state}")
    start_orchestrator(experiment_id)
    return {"status": "started"}


@router.post("/{experiment_id}/stop")
async def stop_experiment(experiment_id: str) -> dict[str, str]:
    orch = get_orchestrator(experiment_id)
    if orch is None:
        raise HTTPException(409, "experiment is not running")
    await orch.request_stop()
    return {"status": "stopping"}


@router.get("/{experiment_id}/events")
def get_events(experiment_id: str, limit: int = 500) -> list[dict[str, Any]]:
    with session_scope() as db:
        rows = db.scalars(
            select(EventRow)
            .where(EventRow.experiment_id == experiment_id)
            .order_by(EventRow.ts.desc())
            .limit(limit)
        ).all()
        return [
            {"id": r.id, "ts": r.ts, "type": r.type, "message": r.message,
             "severity": r.severity, "payload": json.loads(r.payload_json or "{}")}
            for r in reversed(rows)
        ]


@router.get("/{experiment_id}/report")
def get_report(experiment_id: str) -> dict[str, str]:
    with session_scope() as db:
        row = db.get(ExperimentRow, experiment_id)
        if row is None:
            raise HTTPException(404, "experiment not found")
        workspace = Path(row.workspace)
    report = workspace / "REPORT.md"
    if not report.is_file():
        raise HTTPException(404, "report not generated yet")
    return {"markdown": report.read_text(encoding="utf-8")}


@router.get("/{experiment_id}/package")
def get_package_manifest(experiment_id: str) -> dict[str, Any]:
    with session_scope() as db:
        row = db.get(ExperimentRow, experiment_id)
        if row is None:
            raise HTTPException(404, "experiment not found")
        workspace = Path(row.workspace)
    manifest = workspace / "manifest.yaml"
    if not manifest.is_file():
        raise HTTPException(404, "package not generated yet")
    return {"manifest": yaml.safe_load(manifest.read_text(encoding="utf-8")), "workspace": str(workspace)}
