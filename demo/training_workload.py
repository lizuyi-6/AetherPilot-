"""AetherPilot demo training workload.

A REAL Python training-style process with a stable log format, real checkpoint
files, and deterministic, config-causal fault injection for demos:

  - OOM fires only when  step == --inject-oom-at-step  AND  batch_size > --oom-if-batch-size-above
    → after the agent reduces batch size, resuming no longer OOMs. The fix is causal.
  - NaN fires only when  step == --inject-nan-at-step  AND  lr > --nan-if-lr-above
    → after the agent lowers LR + clips gradients, resuming no longer NaNs.

Log format (stdout):
    STEP 12 loss=1.234 lr=0.00002 epoch=0.4
    CHECKPOINT SAVED checkpoint-10
    EVAL macro_f1=0.9437
    TRAINING COMPLETE

This is a DEMO WORKLOAD (labeled as such in the UI): it simulates a fine-tuning
loop without a framework so detection/recovery/orchestration can be exercised
deterministically. Faults are Controlled Fault Injection.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

LOSS_START = 2.30
LOSS_FLOOR = 0.05
LOSS_TAU = 12.0
CKPT_EVERY = 10


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AetherPilot demo training workload")
    p.add_argument("--steps", type=int, default=60)
    p.add_argument("--checkpoint-dir", type=Path, required=True)
    p.add_argument("--resume-from-checkpoint", type=Path, default=None)
    p.add_argument("--checkpoint-every", type=int, default=CKPT_EVERY)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--grad-accum", type=int, default=1)
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--grad-clip", type=float, default=0.0)
    p.add_argument("--gradient-checkpointing", choices=["true", "false"], default="false")
    p.add_argument("--seq-len", type=int, default=2048)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--step-delay", type=float, default=0.25)
    p.add_argument("--dataset-size", type=int, default=960)
    # Controlled fault injection (config-causal)
    p.add_argument("--inject-oom-at-step", type=int, default=0)
    p.add_argument("--oom-if-batch-size-above", type=int, default=16)
    p.add_argument("--inject-nan-at-step", type=int, default=0)
    p.add_argument("--nan-if-lr-above", type=float, default=1.8e-5)
    # Evaluation
    p.add_argument("--eval-only", action="store_true")
    p.add_argument("--eval-checkpoint", type=Path, default=None)
    return p.parse_args()


def loss_at(step: int, seed: int) -> float:
    rng = random.Random(seed * 100_000 + step)
    base = LOSS_FLOOR + (LOSS_START - LOSS_FLOOR) * math.exp(-step / LOSS_TAU)
    noise = rng.uniform(-0.015, 0.015)
    return round(max(LOSS_FLOOR, base + noise), 4)


def save_checkpoint(ckpt_dir: Path, step: int, loss: float, args: argparse.Namespace) -> Path:
    path = ckpt_dir / f"checkpoint-{step}"
    path.mkdir(parents=True, exist_ok=True)
    (path / "meta.json").write_text(
        json.dumps(
            {
                "step": step,
                "loss": loss,
                "lr": args.lr,
                "batch_size": args.batch_size,
                "grad_accum": args.grad_accum,
                "seed": args.seed,
                "saved_at": time.time(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # A real (small) binary payload so checkpoints are tangible artifacts.
    (path / "model.bin").write_bytes(f"AETHER-DEMO-WEIGHTS step={step} loss={loss}".encode())
    return path


def load_checkpoint(path: Path) -> dict:
    meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
    return meta


def run_eval(args: argparse.Namespace) -> int:
    ckpt = args.eval_checkpoint
    if ckpt is None or not (ckpt / "meta.json").is_file():
        print("EVAL ERROR: checkpoint not found", file=sys.stderr)
        return 2
    meta = load_checkpoint(ckpt)
    final_loss = float(meta["loss"])
    # Deterministic mapping from final training loss to the eval metric.
    macro_f1 = round(1.0 - final_loss, 4)
    print(f"EVAL checkpoint={ckpt.name} step={meta['step']} macro_f1={macro_f1:.4f} samples=960")
    return 0


def main() -> int:
    args = parse_args()
    if args.eval_only:
        return run_eval(args)

    ckpt_dir: Path = args.checkpoint_dir
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    start_step = 1
    if args.resume_from_checkpoint is not None:
        meta = load_checkpoint(args.resume_from_checkpoint)
        start_step = int(meta["step"]) + 1
        print(f"RESUMED from {args.resume_from_checkpoint.name} at step {meta['step']}", flush=True)

    effective_batch = args.batch_size * args.grad_accum
    steps_per_epoch = max(1, args.dataset_size // max(1, effective_batch))

    print(
        f"CONFIG batch_size={args.batch_size} grad_accum={args.grad_accum} "
        f"effective_batch={effective_batch} lr={args.lr} grad_clip={args.grad_clip} "
        f"gradient_checkpointing={args.gradient_checkpointing} seq_len={args.seq_len} "
        f"seed={args.seed} steps={args.steps}",
        flush=True,
    )

    for step in range(start_step, args.steps + 1):
        time.sleep(args.step_delay)
        loss = loss_at(step, args.seed)
        epoch = round(step / steps_per_epoch, 2)

        if (
            args.inject_oom_at_step
            and step == args.inject_oom_at_step
            and args.batch_size > args.oom_if_batch_size_above
        ):
            # Simulated activation-memory demand scales with batch geometry
            # (hidden=4096, fp16, ~17x per-element activation factor).
            demand_gb = round(args.batch_size * args.seq_len * 4096 * 2 * 17 / 1024**3, 1)
            capacity_gb = float(os.environ.get("AETHER_DEMO_GPU_GB", "12.0"))
            print(f"STEP {step} loss={loss} lr={args.lr} epoch={epoch}", flush=True)
            print(
                "Traceback (most recent call last):\n"
                '  File "train.py", line 214, in training_step\n'
                "    loss.backward()\n"
                f"RuntimeError: CUDA out of memory. Tried to allocate {demand_gb} GiB "
                f"(GPU 0; {capacity_gb} GiB total capacity; "
                f"{round(capacity_gb * 0.78, 1)} GiB already allocated; "
                f"{round(capacity_gb * 0.09, 1)} GiB free; "
                f"{round(capacity_gb * 0.87, 1)} GiB reserved in total by PyTorch). "
                f"phase=backward step={step}",
                file=sys.stderr,
                flush=True,
            )
            return 1

        if (
            args.inject_nan_at_step
            and step == args.inject_nan_at_step
            and args.lr > args.nan_if_lr_above
        ):
            print(f"STEP {step} loss=nan lr={args.lr} epoch={epoch}", flush=True)
            print(
                f"ERROR: loss became NaN at step {step}; grad_norm=inf; aborting to protect weights",
                file=sys.stderr,
                flush=True,
            )
            return 1

        print(f"STEP {step} loss={loss} lr={args.lr} epoch={epoch}", flush=True)

        if step % args.checkpoint_every == 0 or step == args.steps:
            path = save_checkpoint(ckpt_dir, step, loss, args)
            print(f"CHECKPOINT SAVED {path.name}", flush=True)

    print("TRAINING COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
