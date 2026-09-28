"""Evaluation runner: evaluate a checkpoint and parse the resulting metrics."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from ..training.checkpoint import Checkpoint


async def evaluate_checkpoint(workload: Path, checkpoint: Checkpoint, cwd: Path) -> dict[str, float | str | int]:
    argv = [
        sys.executable,
        str(workload),
        "--checkpoint-dir", str(checkpoint.path.parent),
        "--eval-only",
        "--eval-checkpoint", str(checkpoint.path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"evaluation failed: {stderr.decode(errors='replace')[:500]}")
    metrics: dict[str, float | str | int] = {"checkpoint": checkpoint.name, "step": checkpoint.step}
    for token in stdout.decode(errors="replace").split():
        if "=" in token:
            key, _, value = token.partition("=")
            try:
                metrics[key] = float(value)
            except ValueError:
                metrics[key] = value
    return metrics
