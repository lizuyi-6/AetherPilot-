"""Post-recovery verification.

A recovery is only marked RECOVERY SUCCESSFUL after the resumed process proves:
  - process alive
  - training step advances beyond the resume point
  - loss is finite
  - observed VRAM (when available) stays under the contract limit
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..training.parser import TrainingProgress


@dataclass
class RecoveryVerdict:
    ok: bool
    checks: dict[str, bool]
    detail: str


def verify_recovery(
    progress: TrainingProgress,
    resume_step: int,
    process_alive: bool,
    peak_vram_gb: float | None,
    vram_limit_gb: float,
) -> RecoveryVerdict:
    checks = {
        "process_alive": process_alive,
        "step_advancing": progress.step > resume_step,
        "loss_finite": progress.loss is not None and math.isfinite(progress.loss),
        "vram_within_contract": peak_vram_gb is None or peak_vram_gb <= vram_limit_gb,
        "no_new_fault": not progress.saw_oom and not progress.saw_nan,
    }
    ok = all(checks.values())
    failed = [name for name, passed in checks.items() if not passed]
    detail = "all checks passed" if ok else f"failed: {', '.join(failed)}"
    return RecoveryVerdict(ok=ok, checks=checks, detail=detail)
