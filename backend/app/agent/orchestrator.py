"""Experiment orchestrator: drives one experiment through the state machine.

Flow:
  CONTRACTING → PREFLIGHT → PLANNING → PREPARING → RUNNING/MONITORING
      ↳ incident → INCIDENT → DIAGNOSING → RECOVERY_PLANNING
          ↳ semantics-preserving + permitted → RECOVERING → RUNNING (resume+verify)
          ↳ semantic or not permitted       → WAITING_APPROVAL → (approve) RECOVERING
      ↳ done → EVALUATING → PACKAGING → COMPLETED
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func, select

from ..contracts.models import ExperimentContract
from ..contracts.validator import validate_contract
from ..core.config import settings
from ..core.events import Event, EventType, bus
from ..db.database import session_scope
from ..db.models import ApprovalRow, EventRow, ExperimentRow
from ..evaluation.runner import evaluate_checkpoint
from ..incidents.detector import detect_disk_low, detect_from_progress
from ..incidents.manager import list_incidents, persist_incident, update_incident_status
from ..incidents.models import Incident
from ..integrity.classifier import ChangeClass
from ..integrity.guard import IntegrityGuard
from ..recovery.executor import apply_plan
from ..recovery.planner import plan_recovery
from ..recovery.validator import verify_recovery
from ..reproducibility.packager import build_package
from ..telemetry.collector import ExperimentTelemetryCollector
from ..telemetry.gpu import get_gpu_monitor
from ..telemetry.system import docker_status, environment_record, host_info, sample_system
from ..training.checkpoint import last_stable_checkpoint, latest_checkpoint, list_checkpoints
from ..training.launcher import TrainingRun, build_argv, launch, terminate, wait
from .planner import build_plan
from .reasoning import get_reasoner
from .state_machine import ExperimentState, StateMachine

DISK_LOW_THRESHOLD_GB = 5.0
RECOVERY_VERIFY_STEPS = 2

_orchestrators: dict[str, "ExperimentOrchestrator"] = {}


def get_orchestrator(experiment_id: str) -> "ExperimentOrchestrator | None":
    return _orchestrators.get(experiment_id)


def start_orchestrator(experiment_id: str) -> "ExperimentOrchestrator":
    orch = ExperimentOrchestrator(experiment_id)
    _orchestrators[experiment_id] = orch
    orch.task = asyncio.create_task(orch.run())
    return orch


def reconcile_on_startup() -> None:
    """Mark experiments interrupted by a backend restart honestly as FAILED."""
    from sqlalchemy import select

    transient = [
        s.value
        for s in ExperimentState
        if s not in (ExperimentState.COMPLETED, ExperimentState.FAILED, ExperimentState.CANCELLED, ExperimentState.CREATED)
    ]
    with session_scope() as db:
        rows = db.scalars(select(ExperimentRow).where(ExperimentRow.state.in_(transient))).all()
        for row in rows:
            row.state = ExperimentState.FAILED.value
            row.error = "backend restarted while experiment was in flight"


class ExperimentOrchestrator:
    def __init__(self, experiment_id: str) -> None:
        self.experiment_id = experiment_id
        self.task: asyncio.Task[None] | None = None
        self._cancel = asyncio.Event()
        self._approval_futures: dict[str, asyncio.Future[bool]] = {}
        self.integrity = IntegrityGuard()
        self.run_handle: TrainingRun | None = None
        self.telemetry: ExperimentTelemetryCollector | None = None
        self._workspace: Path | None = None
        self._contract: ExperimentContract | None = None
        self._config: dict[str, Any] = {}
        self._sm: StateMachine | None = None

    # ------------------------------------------------------------- utilities

    @property
    def workspace(self) -> Path:
        assert self._workspace is not None
        return self._workspace

    @property
    def contract(self) -> ExperimentContract:
        assert self._contract is not None
        return self._contract

    async def _emit(self, type_: EventType, message: str = "", payload: dict[str, Any] | None = None,
                    severity: str = "info") -> None:
        await bus.emit(
            Event(type=type_, experiment_id=self.experiment_id, message=message,
                  payload=payload or {}, severity=severity)
        )

    def _row(self) -> ExperimentRow:
        with session_scope() as db:
            row = db.get(ExperimentRow, self.experiment_id)
            if row is None:
                raise KeyError(f"experiment {self.experiment_id} not found")
            db.expunge(row)
            return row

    def _update(self, **fields: Any) -> None:
        with session_scope() as db:
            row = db.get(ExperimentRow, self.experiment_id)
            assert row is not None
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = time.time()

    async def _set_state(self, target: ExperimentState) -> None:
        assert self._sm is not None
        self._sm.transition(target)
        self._update(state=target.value)
        await self._emit(EventType.STATE_CHANGED, message=target.value, payload={"state": target.value})

    def resolve_approval(self, approval_id: str, granted: bool) -> bool:
        future = self._approval_futures.get(approval_id)
        if future and not future.done():
            future.set_result(granted)
            return True
        return False

    async def request_stop(self) -> None:
        self._cancel.set()
        if self.run_handle and self.run_handle.alive:
            await terminate(self.run_handle)

    # ------------------------------------------------------------------ main

    async def run(self) -> None:
        try:
            await self._run_inner()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # never leave state dangling
            try:
                self._update(error=str(exc))
                if self._sm and self._sm.state not in (
                    ExperimentState.COMPLETED, ExperimentState.FAILED, ExperimentState.CANCELLED,
                ):
                    self._sm.force(ExperimentState.FAILED)
                    self._update(state=ExperimentState.FAILED.value)
                await self._emit(EventType.EXPERIMENT_FAILED, message=str(exc), severity="error")
            except Exception:
                pass
        finally:
            if self.telemetry:
                await self.telemetry.stop()
            _orchestrators.pop(self.experiment_id, None)

    async def _run_inner(self) -> None:
        row = self._row()
        self._sm = StateMachine(ExperimentState(row.state))
        self._workspace = Path(row.workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)

        await self._contracting(row)
        await self._preflight()
        await self._planning(row)
        await self._preparing()
        await self._training_loop()
        if self._cancel.is_set():
            return
        await self._evaluating()
        await self._packaging()

    # -------------------------------------------------------------- states

    async def _contracting(self, row: ExperimentRow) -> None:
        await self._set_state(ExperimentState.CONTRACTING)
        self._contract = ExperimentContract.model_validate_json(row.contract_json)
        warnings = validate_contract(self._contract)
        for warning in warnings:
            await self._emit(EventType.AGENT_NOTE, message=f"contract warning: {warning}", severity="warning")
        (self.workspace / "contract.yaml").write_text(
            yaml.safe_dump(self._contract.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
        )
        await self._emit(EventType.CONTRACT_CREATED, message=self._contract.experiment.name,
                         payload={"contract": self._contract.model_dump(mode="json")})

    async def _preflight(self) -> None:
        await self._set_state(ExperimentState.PREFLIGHT)
        await self._emit(EventType.SYSTEM_PREFLIGHT_STARTED, message="probing host")

        gpu = get_gpu_monitor().status()
        if gpu.available:
            for g in gpu.gpus:
                await self._emit(EventType.GPU_DETECTED, message=g.name, payload={
                    "name": g.name, "memory_total_mb": g.memory_total_mb,
                    "driver": gpu.driver_version, "source": gpu.source,
                })
        else:
            await self._emit(EventType.GPU_UNAVAILABLE, message=gpu.detail or "no GPU", severity="warning")

        docker = docker_status()
        await self._emit(EventType.DOCKER_CHECKED, message=str(docker["detail"]), payload=docker,
                         severity="info" if docker["available"] else "warning")

        disk = sample_system()
        await self._emit(EventType.STORAGE_CHECKED, payload={
            "disk_free_gb": disk.disk_free_gb, "disk_total_gb": disk.disk_total_gb,
            "ram_total_gb": disk.ram_total_gb,
        })
        if disk.disk_free_gb < DISK_LOW_THRESHOLD_GB:
            raise RuntimeError(f"insufficient disk: {disk.disk_free_gb:.1f}GB free")

        env = environment_record()
        env["host"] = host_info().__dict__
        (self.workspace / "environment.json").write_text(json.dumps(env, indent=2, default=str), encoding="utf-8")
        await self._emit(EventType.ENVIRONMENT_RECORDED, payload={"python": env.get("python")})

        # Dataset hash (demo dataset is a real file; real mode would resolve the granted path).
        dataset_file = settings.project_root / "demo" / "data" / "aether-v03.jsonl"
        if dataset_file.is_file() and self.contract.reproducibility.dataset_hash:
            digest = hashlib.sha256(dataset_file.read_bytes()).hexdigest()
            (self.workspace / "dataset.sha256").write_text(digest + "\n", encoding="utf-8")
            await self._emit(EventType.DATASET_HASHED, message=dataset_file.name,
                             payload={"sha256": digest, "samples": sum(1 for _ in dataset_file.open())})

        await self._emit(EventType.PREFLIGHT_COMPLETED, message="all preflight checks passed")

    async def _planning(self, row: ExperimentRow) -> None:
        await self._set_state(ExperimentState.PLANNING)
        parsed_goal = json.loads(row.plan_json).get("parsed_goal", {}) if row.plan_json else {}
        gpu = get_gpu_monitor().status()
        vram = gpu.gpus[0].memory_total_mb / 1024 if gpu.available and gpu.gpus else None
        plan = build_plan(self.contract.goal.description, parsed_goal, vram)
        demo_cfg = json.loads(row.config_json).get("demo", {}) if row.config_json else {}
        self._config = {**plan.training_config, "demo": demo_cfg}

        # Rough resource estimate — estimate ≠ guarantee; refined by live telemetry later.
        seq = self._config["max_seq_length"]
        batch = self._config["per_device_train_batch_size"]
        est_vram = round(batch * seq * 4 * 40 / 1024**3 + 2.0, 1)
        est = {
            "estimated_vram_gb": est_vram,
            "contract_vram_gb": self.contract.constraints.max_vram_gb,
            "estimated_disk_gb": 0.05,
            "estimated_runtime_s": self._config["max_steps"] * demo_cfg.get("step_delay", 0.25),
            "risk": "HIGH" if est_vram > self.contract.constraints.max_vram_gb else
                    ("MEDIUM" if est_vram > 0.7 * self.contract.constraints.max_vram_gb else "LOW"),
            "note": "estimate != guarantee — live telemetry refines this at runtime",
        }
        await self._emit(EventType.RESOURCE_ESTIMATED, payload=est,
                         severity="warning" if est["risk"] == "HIGH" else "info")
        await self._emit(EventType.EXPERIMENT_PLAN_CREATED,
                         message=f"{len(plan.steps)} steps",
                         payload={"steps": [s.model_dump() for s in plan.steps], "config": self._config})

    async def _preparing(self) -> None:
        await self._set_state(ExperimentState.PREPARING)
        configs_dir = self.workspace / "configs"
        configs_dir.mkdir(parents=True, exist_ok=True)
        (configs_dir / "original.yaml").write_text(yaml.safe_dump(self._config, sort_keys=True), encoding="utf-8")
        (configs_dir / "current.yaml").write_text(yaml.safe_dump(self._config, sort_keys=True), encoding="utf-8")
        self._update(config_json=json.dumps(self._config), original_config_json=json.dumps(self._config))
        await self._emit(EventType.CONFIG_GENERATED, payload={"config": self._config})
        self.telemetry = ExperimentTelemetryCollector(self.experiment_id, self.workspace)
        await self.telemetry.start()

    async def _training_loop(self) -> None:
        """Launch → monitor → incident/recovery loop until done, cancelled, or failed."""
        resume_from: Path | None = None
        verify_at_step: int | None = None

        while not self._cancel.is_set():
            await self._set_state(ExperimentState.RUNNING)
            ckpt_dir = self.workspace / "checkpoints"
            argv = build_argv(self._config, settings.demo_workload_path, ckpt_dir, resume_from)
            self.run_handle = TrainingRun(self.experiment_id, self.workspace)
            await launch(self.run_handle, argv, cwd=settings.project_root,
                         log_path=self.workspace / "logs" / "training.log")
            await self._emit(
                EventType.TRAINING_RESUMED if resume_from else EventType.TRAINING_STARTED,
                message=("resumed from " + resume_from.name) if resume_from else "training process started",
                payload={"argv": " ".join(Path(a).name if a.endswith(".py") else a for a in argv[:6]) + " …"},
            )
            await self._set_state(ExperimentState.MONITORING)

            exit_code = await self._monitor(verify_at_step)
            if self._cancel.is_set():
                await self._set_state(ExperimentState.CANCELLED)
                await self._emit(EventType.EXPERIMENT_CANCELLED, message="cancelled by user")
                return

            progress = self.run_handle.progress
            if exit_code == 0 and progress.step >= self._config["max_steps"]:
                return  # success → evaluation

            incident = detect_from_progress(
                self.experiment_id, progress, exit_code,
                vram_limit_gb=self.contract.constraints.max_vram_gb,
            )
            if incident is None:
                raise RuntimeError(f"training stopped unexpectedly (exit={exit_code}) with no diagnosable signal")

            verdict = await self._handle_incident(incident, progress.step)
            if verdict is None:
                return  # failed inside handler (state already set)
            resume_from, verify_at_step = verdict

    async def _monitor(self, verify_at_step: int | None) -> int:
        """Watch the running process: recovery verification + disk guard, then wait for exit."""
        assert self.run_handle is not None
        handle = self.run_handle
        verified = verify_at_step is None
        last_disk_check = 0.0
        while handle.alive:
            if self._cancel.is_set():
                await terminate(handle)
                break
            if not verified and verify_at_step is not None:
                p = handle.progress
                if p.step > verify_at_step + RECOVERY_VERIFY_STEPS:
                    verdict = verify_recovery(p, verify_at_step, handle.alive, None,
                                              self.contract.constraints.max_vram_gb)
                    if verdict.ok:
                        await self._emit(EventType.RECOVERY_SUCCEEDED, message=verdict.detail,
                                         payload={"checks": verdict.checks})
                        verified = True
                    else:
                        await self._emit(EventType.RECOVERY_FAILED, message=verdict.detail,
                                         payload={"checks": verdict.checks}, severity="error")
                        await terminate(handle)
                        break
            # Disk statvfs is a syscall — sample at most once per second, not per tick.
            if time.monotonic() - last_disk_check >= 1.0:
                last_disk_check = time.monotonic()
                disk = sample_system()
                if disk.disk_free_gb < DISK_LOW_THRESHOLD_GB:
                    incident = detect_disk_low(self.experiment_id, disk.disk_free_gb, DISK_LOW_THRESHOLD_GB)
                    if incident:
                        await terminate(handle)
                        await self._record_incident(incident)
                        raise RuntimeError("disk space exhausted; experiment halted safely")
            await asyncio.sleep(0.25)
        return await wait(handle)

    # ------------------------------------------------------------- incidents

    async def _record_incident(self, incident: Incident) -> None:
        reasoner = get_reasoner()
        explanation = reasoner.explain_incident(incident.type.value, incident.evidence)
        if explanation:
            incident.root_cause = explanation
        persist_incident(incident, self.workspace)
        await self._emit(EventType.INCIDENT_DETECTED, message=incident.type.value,
                         payload=incident.model_dump(mode="json"), severity="error")

    async def _handle_incident(self, incident: Incident, failed_step: int) -> tuple[Path, int] | None:
        """Returns (resume_checkpoint_path, failed_step) or None if the experiment failed."""
        await self._set_state(ExperimentState.INCIDENT)
        await self._record_incident(incident)

        row = self._row()
        if row.recovery_attempts >= self.contract.recovery.max_auto_recovery_attempts:
            await self._emit(EventType.EXPERIMENT_FAILED,
                             message=f"max auto recovery attempts ({row.recovery_attempts}) exhausted",
                             severity="error")
            await self._set_state(ExperimentState.FAILED)
            update_incident_status(incident.id, "FAILED")
            return None

        await self._set_state(ExperimentState.DIAGNOSING)
        await self._emit(EventType.DIAGNOSIS_STARTED, message=incident.type.value)
        ckpt_dir = self.workspace / "checkpoints"
        latest = latest_checkpoint(ckpt_dir, before_step=failed_step + 1)
        stable = last_stable_checkpoint(ckpt_dir, before_step=failed_step + 1)
        await self._emit(EventType.DIAGNOSIS_COMPLETED,
                         message=f"root cause: {incident.root_cause[:120]}",
                         payload={"latest_checkpoint": latest.name if latest else None,
                                  "stable_checkpoint": stable.name if stable else None})

        await self._set_state(ExperimentState.RECOVERY_PLANNING)
        plan = plan_recovery(incident, self._config,
                             latest.name if latest else None, stable.name if stable else None)
        if plan is None:
            await self._emit(EventType.EXPERIMENT_FAILED,
                             message=f"no safe automatic recovery for {incident.type.value}",
                             severity="error")
            await self._set_state(ExperimentState.FAILED)
            update_incident_status(incident.id, "FAILED")
            return None

        # Integrity classification — deterministic.
        assessment = self.integrity.assess(self._config, plan.config_patch) if plan.config_patch else {
            "class": ChangeClass.SEMANTICS_PRESERVING.value, "reasons": ["no config change"], "diff": [],
        }
        self._update(integrity_status=self.integrity.status.value,
                     auto_changes=len(self.integrity.automatic_changes),
                     semantic_changes=len(self.integrity.semantic_changes))
        await self._emit(EventType.INTEGRITY_CHECKED, payload={
            "class": assessment["class"], "reasons": assessment["reasons"],
            **self.integrity.summary(),
        })
        await self._emit(EventType.RECOVERY_PLAN_CREATED, message=plan.strategy, payload={
            "plan": plan.model_dump(), "diff": assessment["diff"], "integrity": assessment["class"],
        })

        # Permission gate: contract decides whether the agent may act alone.
        permitted = (
            self.contract.permissions.modify_training_config
            and self.contract.permissions.restart_training
            and assessment["class"] == ChangeClass.SEMANTICS_PRESERVING.value
        )
        if not permitted:
            approved = await self._wait_for_approval(incident, plan, assessment)
            if not approved:
                await self._emit(EventType.EXPERIMENT_FAILED, message="recovery rejected by user",
                                 severity="error")
                await self._set_state(ExperimentState.FAILED)
                update_incident_status(incident.id, "FAILED")
                return None

        # ---- RECOVERING
        await self._set_state(ExperimentState.RECOVERING)
        update_incident_status(incident.id, "RECOVERING",
                               recovery=plan.model_dump() | {"integrity": assessment["class"]})
        if plan.config_patch:
            self._config, audit = apply_plan(self._config, plan, self.workspace)
            self._update(config_json=json.dumps(self._config),
                         recovery_attempts=row.recovery_attempts + 1)
            await self._emit(EventType.CONFIG_PATCH_APPLIED, message=plan.strategy,
                             payload={"patch": plan.config_patch, "diff": assessment["diff"],
                                      "audit": {"who": audit["who"], "why": audit["why"]}})
        else:
            self._update(recovery_attempts=row.recovery_attempts + 1)

        resume_name = plan.resume_from_checkpoint
        if resume_name is None or not (ckpt_dir / resume_name).is_dir():
            await self._emit(EventType.EXPERIMENT_FAILED,
                             message="no checkpoint available for rollback", severity="error")
            await self._set_state(ExperimentState.FAILED)
            update_incident_status(incident.id, "FAILED")
            return None
        await self._emit(EventType.CHECKPOINT_ROLLBACK, message=resume_name,
                         payload={"from_step": failed_step, "to_checkpoint": resume_name})
        update_incident_status(incident.id, "RESOLVED")
        return ckpt_dir / resume_name, failed_step

    async def _wait_for_approval(self, incident: Incident, plan: Any, assessment: dict) -> bool:
        await self._set_state(ExperimentState.WAITING_APPROVAL)
        with session_scope() as db:
            approval = ApprovalRow(
                experiment_id=self.experiment_id,
                action_json=json.dumps({"plan": plan.model_dump(), "integrity": assessment}),
                reason=(f"{incident.type.value} recovery requires human approval: "
                        f"integrity={assessment['class']}, contract permissions deny autonomous change"),
            )
            db.add(approval)
            db.flush()
            approval_id = approval.id
        await self._emit(EventType.APPROVAL_REQUESTED, message=f"approval {approval_id}",
                         payload={"approval_id": approval_id, "plan": plan.model_dump(),
                                  "integrity": assessment}, severity="warning")
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._approval_futures[approval_id] = future
        granted = await future  # resolved by the approvals API (or cancel)
        self._approval_futures.pop(approval_id, None)
        await self._emit(EventType.APPROVAL_GRANTED if granted else EventType.APPROVAL_REJECTED,
                         message=approval_id)
        return granted

    # ------------------------------------------------------------ completion

    async def _evaluating(self) -> None:
        await self._set_state(ExperimentState.EVALUATING)
        await self._emit(EventType.EVALUATION_STARTED, message="selecting best checkpoint")
        checkpoints = list_checkpoints(self.workspace / "checkpoints")
        if not checkpoints:
            raise RuntimeError("no checkpoints found for evaluation")
        scored = [c for c in checkpoints if c.loss is not None]
        best = min(scored, key=lambda c: c.loss) if scored else checkpoints[-1]
        metrics = await evaluate_checkpoint(settings.demo_workload_path, best, settings.project_root)
        targets = {name: {"target": spec.target, "operator": spec.operator,
                          "observed": metrics.get(name),
                          "pass": isinstance(metrics.get(name), (int, float))
                          and spec.satisfied_by(float(metrics[name]))}
                   for name, spec in self.contract.metrics.items()}
        result = {"metrics": metrics, "targets": targets, "best_checkpoint": best.name}
        self._update(best_checkpoint=best.name, final_metrics_json=json.dumps(result))
        await self._emit(EventType.EVALUATION_COMPLETED, message=f"best={best.name}", payload=result)

    async def _packaging(self) -> None:
        await self._set_state(ExperimentState.PACKAGING)
        row = self._row()
        incidents = list_incidents(self.experiment_id)

        with session_scope() as db:
            events = db.scalars(
                select(EventRow).where(EventRow.experiment_id == self.experiment_id).order_by(EventRow.ts)
            ).all()
            timeline = [{"ts": e.ts, "type": e.type, "message": e.message} for e in events]

        evaluation = json.loads(row.final_metrics_json or "{}")
        with session_scope() as db:
            human_interventions = db.scalar(
                select(func.count()).select_from(ApprovalRow).where(
                    ApprovalRow.experiment_id == self.experiment_id,
                    ApprovalRow.status == "GRANTED",
                )
            ) or 0
        integrity = self.integrity.summary() | {"human_interventions": human_interventions}
        original = json.loads(row.original_config_json or "{}")
        dataset_file = settings.project_root / "demo" / "data" / "aether-v03.jsonl"
        build_package(
            workspace=self.workspace,
            contract=self.contract,
            original_config=original,
            final_config=self._config,
            incidents=incidents,
            evaluation=evaluation,
            integrity_summary=integrity,
            timeline=timeline,
            dataset_path=dataset_file if dataset_file.is_file() else None,
            workload_path=settings.demo_workload_path,
            started_at=row.created_at,
            completed_at=time.time(),
        )
        await self._emit(EventType.PACKAGE_CREATED, message=str(self.workspace))
        self._update(completed_at=time.time())
        await self._set_state(ExperimentState.COMPLETED)
        await self._emit(EventType.EXPERIMENT_COMPLETED, message="experiment completed",
                         payload={"metrics": evaluation, "integrity": integrity})
