"""Training process launcher.

Spawns the training workload as a child process (argv list, no shell), streams
stdout/stderr line-by-line into the parser and the event bus, and reports the
exit code. The launched process is owned by this experiment: terminating it is
always permitted (it is not an "external process").
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import IO, Any

from ..core.events import Event, EventType, bus
from .parser import TrainingLogParser, TrainingProgress


class TrainingRun:
    def __init__(self, experiment_id: str, workspace: Path) -> None:
        self.experiment_id = experiment_id
        self.workspace = workspace
        self.parser = TrainingLogParser()
        self.proc: asyncio.subprocess.Process | None = None
        self.started_at: float | None = None
        self.exit_code: int | None = None
        self.stderr_tail: list[str] = []
        self.log_fh: IO[str] | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None

    @property
    def progress(self) -> TrainingProgress:
        return self.parser.progress

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None


def build_argv(config: dict[str, Any], workload: Path, checkpoint_dir: Path, resume: Path | None) -> list[str]:
    demo = config.get("demo", {})
    argv = [
        sys.executable,
        str(workload),
        "--steps", str(config["max_steps"]),
        "--checkpoint-dir", str(checkpoint_dir),
        "--batch-size", str(config["per_device_train_batch_size"]),
        "--grad-accum", str(config.get("gradient_accumulation_steps", 1)),
        "--lr", str(config["learning_rate"]),
        "--grad-clip", str(config.get("max_grad_norm", 0.0)),
        "--gradient-checkpointing", "true" if config.get("gradient_checkpointing") else "false",
        "--seq-len", str(config.get("max_seq_length", 2048)),
        "--seed", str(config.get("seed", 42)),
        "--step-delay", str(demo.get("step_delay", 0.25)),
    ]
    if demo.get("inject_oom_at_step"):
        argv += ["--inject-oom-at-step", str(demo["inject_oom_at_step"])]
        argv += ["--oom-if-batch-size-above", str(demo.get("oom_if_batch_size_above", 16))]
    if demo.get("inject_nan_at_step"):
        argv += ["--inject-nan-at-step", str(demo["inject_nan_at_step"])]
        argv += ["--nan-if-lr-above", str(demo.get("nan_if_lr_above", 1.8e-5))]
    if resume is not None:
        argv += ["--resume-from-checkpoint", str(resume)]
    return argv


async def launch(run: TrainingRun, argv: list[str], cwd: Path, log_path: Path) -> None:
    run.started_at = time.time()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    run.log_fh = log_path.open("a", encoding="utf-8")

    run.proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def pump(stream: asyncio.StreamReader, is_err: bool) -> None:
        last_emitted_ckpt: str | None = None
        while True:
            raw = await stream.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\n")
            assert run.log_fh is not None
            run.log_fh.write(("STDERR " if is_err else "") + line + "\n")
            run.log_fh.flush()
            if is_err:
                run.stderr_tail.append(line)
                run.stderr_tail = run.stderr_tail[-50:]
            run.parser.feed_line(line)
            p = run.progress
            if p.step:
                await bus.emit(
                    Event(
                        type=EventType.TRAINING_PROGRESS,
                        experiment_id=run.experiment_id,
                        payload={
                            "step": p.step,
                            "max_steps": p.max_steps,
                            "loss": p.loss if p.loss == p.loss else str(p.loss),
                            "lr": p.lr,
                            "epoch": p.epoch,
                            "last_checkpoint": p.last_checkpoint,
                        },
                    )
                )
            if p.last_checkpoint and p.last_checkpoint != last_emitted_ckpt:
                last_emitted_ckpt = p.last_checkpoint
                await bus.emit(
                    Event(
                        type=EventType.CHECKPOINT_CREATED,
                        experiment_id=run.experiment_id,
                        message=f"checkpoint {p.last_checkpoint}",
                        payload={"checkpoint": p.last_checkpoint, "step": p.step},
                    )
                )

    assert run.proc.stdout and run.proc.stderr
    run._stdout_task = asyncio.create_task(pump(run.proc.stdout, is_err=False))
    run._stderr_task = asyncio.create_task(pump(run.proc.stderr, is_err=True))


async def wait(run: TrainingRun) -> int:
    assert run.proc is not None
    run.exit_code = await run.proc.wait()
    if run._stdout_task:
        await asyncio.gather(run._stdout_task, run._stderr_task, return_exceptions=True)
    if run.log_fh:
        run.log_fh.close()
        run.log_fh = None
    return run.exit_code


async def terminate(run: TrainingRun) -> None:
    if run.proc and run.proc.returncode is None:
        run.proc.terminate()
        try:
            await asyncio.wait_for(run.proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            run.proc.kill()
            await run.proc.wait()
