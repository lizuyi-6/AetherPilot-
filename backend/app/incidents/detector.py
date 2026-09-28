"""Incident detectors. Deterministic rules over parsed logs and telemetry.

Detectors never call the LLM; they produce structured evidence. The LLM (when
configured) may later *explain* an incident, but detection itself is rule-based.
"""

from __future__ import annotations

from ..incidents.models import Incident, IncidentType, Severity
from ..training.parser import TrainingProgress


def detect_from_progress(
    experiment_id: str,
    progress: TrainingProgress,
    exit_code: int | None,
    vram_limit_gb: float,
    peak_vram_gb: float | None = None,
) -> Incident | None:
    """Produce an Incident from observed training state, or None."""
    if progress.saw_oom:
        evidence = ["CUDA out of memory raised by training process"]
        if progress.oom_line:
            evidence.append(f"log: {progress.oom_line[:200]}")
        if peak_vram_gb is not None:
            evidence.append(f"peak_vram={peak_vram_gb:.1f}GB (contract limit {vram_limit_gb:.0f}GB)")
        evidence.append(f"failed_at_step={progress.step}")
        return Incident(
            experiment_id=experiment_id,
            type=IncidentType.CUDA_OOM,
            severity=Severity.HIGH,
            evidence=evidence,
            root_cause="Training allocation exceeded available VRAM at current batch configuration.",
            confidence=0.95,
            recommended_actions=[
                "reduce per-device batch size",
                "increase gradient accumulation to preserve effective batch",
                "enable gradient checkpointing",
            ],
            extra={"step": progress.step, "peak_vram_gb": peak_vram_gb},
        )

    if progress.saw_nan:
        evidence = [f"non-finite loss observed at step {progress.step}"]
        if progress.loss_history:
            prev = [(s, l) for s, l in progress.loss_history if l == l]  # finite only
            if prev:
                s, l = prev[-1]
                evidence.append(f"last finite loss={l:.4f} at step {s}")
        if progress.lr is not None:
            evidence.append(f"lr={progress.lr}")
        return Incident(
            experiment_id=experiment_id,
            type=IncidentType.NAN_LOSS,
            severity=Severity.HIGH,
            evidence=evidence,
            root_cause="Loss became NaN/Inf — typically learning-rate instability or gradient explosion.",
            confidence=0.9,
            recommended_actions=[
                "roll back to last stable checkpoint",
                "reduce learning rate",
                "enable gradient clipping",
            ],
            extra={"step": progress.step, "lr": progress.lr},
        )

    if exit_code is not None and exit_code != 0:
        return Incident(
            experiment_id=experiment_id,
            type=IncidentType.PROCESS_CRASH,
            severity=Severity.MEDIUM,
            evidence=[f"training process exited with code {exit_code}", f"last_step={progress.step}"],
            root_cause="Training process terminated abnormally without a recognized signature.",
            confidence=0.6,
            recommended_actions=["resume from latest checkpoint"],
            extra={"step": progress.step, "exit_code": exit_code},
        )
    return None


def detect_disk_low(experiment_id: str, free_gb: float, threshold_gb: float) -> Incident | None:
    if free_gb >= threshold_gb:
        return None
    return Incident(
        experiment_id=experiment_id,
        type=IncidentType.DISK_LOW,
        severity=Severity.CRITICAL,
        evidence=[f"disk_free={free_gb:.1f}GB below safety threshold {threshold_gb:.1f}GB"],
        root_cause="Workspace disk nearly exhausted; checkpoints would become unwritable.",
        confidence=1.0,
        recommended_actions=["pause experiment", "free disk space (requires human)"],
    )


def detect_gpu_unavailable(experiment_id: str) -> Incident:
    return Incident(
        experiment_id=experiment_id,
        type=IncidentType.GPU_UNAVAILABLE,
        severity=Severity.CRITICAL,
        evidence=["no NVIDIA GPU visible via pynvml or nvidia-smi"],
        root_cause="GPU runtime unavailable on this host.",
        confidence=1.0,
        recommended_actions=["check driver/runtime", "or run in Demo Mode"],
    )
