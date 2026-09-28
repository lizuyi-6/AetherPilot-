"""Checkpoint discovery and selection.

Checkpoints live in <workspace>/checkpoints/checkpoint-<step>/ and contain a
meta.json with at least {"step": int, "loss": float}. Discovery is deterministic
filesystem scanning — never delegated to the LLM.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_CKPT_DIR_RE = re.compile(r"^checkpoint-(\d+)$")


@dataclass
class Checkpoint:
    step: int
    path: Path
    loss: float | None

    @property
    def name(self) -> str:
        return f"checkpoint-{self.step}"


def list_checkpoints(checkpoint_dir: Path) -> list[Checkpoint]:
    if not checkpoint_dir.is_dir():
        return []
    found: list[Checkpoint] = []
    for child in checkpoint_dir.iterdir():
        match = _CKPT_DIR_RE.match(child.name)
        if not match or not child.is_dir():
            continue
        step = int(match.group(1))
        loss: float | None = None
        meta_file = child / "meta.json"
        if meta_file.is_file():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                raw_loss = meta.get("loss")
                if isinstance(raw_loss, (int, float)):
                    loss = float(raw_loss)
            except (json.JSONDecodeError, OSError):
                pass
        found.append(Checkpoint(step=step, path=child, loss=loss))
    return sorted(found, key=lambda c: c.step)


def latest_checkpoint(checkpoint_dir: Path, before_step: int | None = None) -> Checkpoint | None:
    """Latest checkpoint strictly before `before_step` (the crashing step)."""
    candidates = list_checkpoints(checkpoint_dir)
    if before_step is not None:
        candidates = [c for c in candidates if c.step < before_step]
    return candidates[-1] if candidates else None


def last_stable_checkpoint(checkpoint_dir: Path, before_step: int | None = None) -> Checkpoint | None:
    """Latest checkpoint whose recorded loss is finite — used for NaN rollback."""
    import math

    candidates = list_checkpoints(checkpoint_dir)
    if before_step is not None:
        candidates = [c for c in candidates if c.step < before_step]
    stable = [c for c in candidates if c.loss is not None and math.isfinite(c.loss)]
    if stable:
        return stable[-1]
    return candidates[-1] if candidates else None
