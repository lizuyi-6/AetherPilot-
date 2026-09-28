"""FastAPI application entrypoint.

Lifespan:
  startup — init DB, reconcile interrupted experiments, start telemetry,
            register event persistence.
  shutdown — stop telemetry collectors.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agent.orchestrator import reconcile_on_startup
from .api import experiments, incidents, skills, system, ws
from .core.events import Event, EventType, bus
from .core.config import settings
from .db.database import init_db, session_scope
from .db.models import EventRow
from .telemetry.collector import system_collector


def _persist_event(event: Event) -> None:
    # Telemetry samples are high-frequency; persist everything else.
    if event.type is EventType.TELEMETRY_SAMPLE:
        return
    with session_scope() as db:
        db.add(EventRow(
            id=event.id,
            ts=event.ts,
            experiment_id=event.experiment_id,
            type=event.type.value,
            message=event.message,
            payload_json=json.dumps(event.payload, default=str),
            severity=event.severity,
        ))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    reconcile_on_startup()
    bus.add_persist_hook(_persist_event)
    await system_collector.start()
    yield
    await system_collector.stop()


app = FastAPI(title="AetherPilot", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(experiments.router)
app.include_router(incidents.incidents_router)
app.include_router(skills.router)
app.include_router(ws.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "aetherpilot"}


@app.get("/api/scenarios")
def scenarios() -> list[dict]:
    """Curated demo scenarios (A-D) for the hackathon walkthrough."""
    base_goal = (
        "Fine-tune Qwen3-4B on dataset/aether-v03. Target Macro-F1 >= 0.92. "
        "Complete within 6 hours. Keep VRAM under 100 GB."
    )
    return [
        {
            "id": "A",
            "title": "Clean run",
            "description": "Normal experiment, no injected faults.",
            "request": {"name": "scenario-a-clean-run", "goal": base_goal, "mode": "demo",
                        "demo": {"step_delay": 0.2}},
        },
        {
            "id": "B",
            "title": "CUDA OOM → autonomous recovery",
            "description": "Injected OOM at step 20; agent shrinks batch, preserves effective batch, resumes.",
            "request": {"name": "scenario-b-oom-recovery", "goal": base_goal, "mode": "demo",
                        "demo": {"inject_oom_at_step": 20, "step_delay": 0.2}},
        },
        {
            "id": "C",
            "title": "OOM + NaN → two recoveries",
            "description": "Full demo: OOM recovery, then NaN rollback with LR reduction + grad clipping.",
            "request": {"name": "scenario-c-oom-nan", "goal": base_goal, "mode": "demo",
                        "demo": {"inject_oom_at_step": 20, "inject_nan_at_step": 45, "step_delay": 0.2}},
        },
        {
            "id": "D",
            "title": "Approval-gated recovery",
            "description": "Contract forbids autonomous config changes — the agent must wait for human approval.",
            "request": {"name": "scenario-d-approval", "goal": base_goal, "mode": "demo",
                        "demo": {"inject_oom_at_step": 20, "step_delay": 0.2},
                        "contract_overrides": {"permissions": {"modify_training_config": False}}},
        },
    ]
