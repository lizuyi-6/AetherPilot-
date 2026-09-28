"""Recovery planning: deterministic incident-type → config-patch strategies.

The planner proposes; the IntegrityGuard classifies; the contract permits;
the executor acts. Recovery verification is a separate step (validator.py).
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field

from ..incidents.models import Incident, IncidentType


class RecoveryPlan(BaseModel):
    incident_id: str
    strategy: str
    config_patch: dict[str, Any] = Field(default_factory=dict)
    resume_from_checkpoint: str | None = None  # checkpoint dir name
    explanation: str = ""
    requires_approval: bool = False


def plan_recovery(
    incident: Incident,
    config: dict[str, Any],
    checkpoint_name: str | None,
    stable_checkpoint_name: str | None,
) -> RecoveryPlan | None:
    """Deterministic recovery policy. Returns None when no safe automatic plan exists."""

    if incident.type is IncidentType.CUDA_OOM:
        batch = config.get("per_device_train_batch_size")
        if not isinstance(batch, (int, float)) or batch <= 1:
            return None  # cannot shrink further automatically
        new_batch = max(1, int(batch) // 4)
        shrink_factor = int(batch) // new_batch
        accum = int(config.get("gradient_accumulation_steps", 1))
        patch: dict[str, Any] = {
            "per_device_train_batch_size": new_batch,
            "gradient_accumulation_steps": accum * shrink_factor,
            "gradient_checkpointing": True,
        }
        return RecoveryPlan(
            incident_id=incident.id,
            strategy="oom_batch_reduction",
            config_patch=patch,
            resume_from_checkpoint=checkpoint_name,
            explanation=(
                f"Reduce per-device batch {int(batch)} → {new_batch} and raise gradient "
                f"accumulation {accum} → {accum * shrink_factor} to keep the effective batch "
                f"size at {int(batch) * accum}. Enable gradient checkpointing to trade compute "
                "for memory. Resume from the last checkpoint."
            ),
        )

    if incident.type is IncidentType.NAN_LOSS:
        lr = config.get("learning_rate")
        if not isinstance(lr, (int, float)) or not math.isfinite(lr):
            return None
        new_lr = round(lr * 0.75, 10)
        patch = {
            "learning_rate": new_lr,
            "max_grad_norm": 1.0,
        }
        return RecoveryPlan(
            incident_id=incident.id,
            strategy="nan_rollback",
            config_patch=patch,
            resume_from_checkpoint=stable_checkpoint_name or checkpoint_name,
            explanation=(
                f"Roll back to last stable checkpoint, reduce learning rate {lr} → {new_lr}, "
                "enable gradient clipping (max_grad_norm=1.0) to damp gradient explosion."
            ),
        )

    if incident.type is IncidentType.PROCESS_CRASH:
        if checkpoint_name is None:
            return None
        return RecoveryPlan(
            incident_id=incident.id,
            strategy="crash_resume",
            config_patch={},
            resume_from_checkpoint=checkpoint_name,
            explanation="Resume unchanged configuration from the latest checkpoint.",
        )

    # DISK_LOW / GPU_UNAVAILABLE: no safe automatic config change.
    return None
