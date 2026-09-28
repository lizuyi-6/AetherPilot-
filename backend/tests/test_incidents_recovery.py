"""Incident detection + recovery planning + verification tests."""

from __future__ import annotations

from app.incidents.detector import detect_disk_low, detect_from_progress
from app.incidents.models import IncidentType
from app.recovery.planner import plan_recovery
from app.recovery.validator import verify_recovery
from app.training.parser import TrainingLogParser

BASE_CONFIG = {
    "per_device_train_batch_size": 32,
    "gradient_accumulation_steps": 1,
    "learning_rate": 2e-5,
    "max_grad_norm": 0.0,
    "gradient_checkpointing": False,
    "max_steps": 80,
}


def _progress(lines: list[str]) -> TrainingLogParser:
    p = TrainingLogParser()
    for line in lines:
        p.feed_line(line)
    return p


def test_oom_detection() -> None:
    p = _progress(["STEP 19 loss=0.4", "RuntimeError: CUDA out of memory. Tried to allocate 3.8 GiB"])
    incident = detect_from_progress("exp", p.progress, exit_code=1, vram_limit_gb=100)
    assert incident is not None
    assert incident.type is IncidentType.CUDA_OOM
    assert incident.confidence >= 0.9


def test_nan_detection() -> None:
    p = _progress(["STEP 44 loss=0.2", "STEP 45 loss=nan"])
    incident = detect_from_progress("exp", p.progress, exit_code=1, vram_limit_gb=100)
    assert incident is not None
    assert incident.type is IncidentType.NAN_LOSS


def test_generic_crash_detection() -> None:
    p = _progress(["STEP 5 loss=1.0"])
    incident = detect_from_progress("exp", p.progress, exit_code=137, vram_limit_gb=100)
    assert incident is not None
    assert incident.type is IncidentType.PROCESS_CRASH


def test_clean_exit_no_incident() -> None:
    p = _progress(["STEP 80 loss=0.06"])
    assert detect_from_progress("exp", p.progress, exit_code=0, vram_limit_gb=100) is None


def test_disk_low_threshold() -> None:
    assert detect_disk_low("exp", free_gb=10, threshold_gb=5) is None
    incident = detect_disk_low("exp", free_gb=3, threshold_gb=5)
    assert incident is not None and incident.type is IncidentType.DISK_LOW


def test_oom_recovery_plan_preserves_effective_batch() -> None:
    p = _progress(["RuntimeError: CUDA out of memory"])
    incident = detect_from_progress("exp", p.progress, 1, 100)
    plan = plan_recovery(incident, BASE_CONFIG, "checkpoint-10", "checkpoint-10")
    assert plan is not None
    assert plan.strategy == "oom_batch_reduction"
    assert plan.config_patch["per_device_train_batch_size"] == 8
    assert plan.config_patch["gradient_accumulation_steps"] == 4
    assert plan.config_patch["gradient_checkpointing"] is True
    assert plan.resume_from_checkpoint == "checkpoint-10"


def test_nan_recovery_plan() -> None:
    p = _progress(["STEP 45 loss=nan"])
    incident = detect_from_progress("exp", p.progress, 1, 100)
    plan = plan_recovery(incident, BASE_CONFIG, "checkpoint-40", "checkpoint-30")
    assert plan is not None
    assert plan.strategy == "nan_rollback"
    assert abs(plan.config_patch["learning_rate"] - 1.5e-5) < 1e-12
    assert plan.config_patch["max_grad_norm"] == 1.0
    assert plan.resume_from_checkpoint == "checkpoint-30"  # stable, not latest


def test_crash_resume_plan() -> None:
    p = _progress(["STEP 5 loss=1.0"])
    incident = detect_from_progress("exp", p.progress, 137, 100)
    plan = plan_recovery(incident, BASE_CONFIG, "checkpoint-5", "checkpoint-5")
    assert plan is not None
    assert plan.strategy == "crash_resume"
    assert plan.config_patch == {}


def test_no_plan_when_batch_cannot_shrink() -> None:
    p = _progress(["RuntimeError: CUDA out of memory"])
    incident = detect_from_progress("exp", p.progress, 1, 100)
    assert plan_recovery(incident, {**BASE_CONFIG, "per_device_train_batch_size": 1}, "c", "c") is None


def test_disk_low_has_no_auto_plan() -> None:
    incident = detect_disk_low("exp", 1.0, 5.0)
    assert plan_recovery(incident, BASE_CONFIG, "c", "c") is None


def test_recovery_verification() -> None:
    p = _progress(["STEP 11 loss=0.5", "STEP 12 loss=0.49", "STEP 13 loss=0.48"])
    verdict = verify_recovery(p.progress, resume_step=10, process_alive=True, peak_vram_gb=20, vram_limit_gb=100)
    assert verdict.ok

    bad = verify_recovery(p.progress, resume_step=10, process_alive=False, peak_vram_gb=None, vram_limit_gb=100)
    assert not bad.ok
    assert bad.checks["process_alive"] is False


def test_recovery_verification_rejects_nan() -> None:
    p = _progress(["STEP 12 loss=nan"])
    verdict = verify_recovery(p.progress, resume_step=10, process_alive=True, peak_vram_gb=None, vram_limit_gb=100)
    assert not verdict.ok
    assert verdict.checks["no_new_fault"] is False
