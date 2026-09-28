"""Training log parser.

Parses stable-format lines emitted by training loops:

    STEP 1834 loss=0.082 lr=0.00002 epoch=1.2
    CHECKPOINT SAVED checkpoint-2000
    EVAL macro_f1=0.9437

Also surfaces raw anomaly signals (OOM text, nan loss) for the incident detector.
The parser is deterministic; no LLM is involved in detection.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

_STEP_RE = re.compile(r"\bSTEP\s+(\d+)\b", re.IGNORECASE)
_KV_RE = re.compile(r"(\w+)=([^\s]+)")
_CHECKPOINT_RE = re.compile(r"CHECKPOINT\s+SAVED\s+(\S+)", re.IGNORECASE)
_OOM_RE = re.compile(r"(CUDA out of memory|OutOfMemoryError|CUDA error: out of memory)", re.IGNORECASE)
_EVAL_RE = re.compile(r"\bEVAL\b", re.IGNORECASE)


@dataclass
class TrainingProgress:
    step: int = 0
    max_steps: int = 0
    loss: float | None = None
    lr: float | None = None
    epoch: float | None = None
    last_checkpoint: str | None = None
    loss_history: list[tuple[int, float]] = field(default_factory=list)
    eval_metrics: dict[str, float] = field(default_factory=dict)
    saw_nan: bool = False
    saw_oom: bool = False
    oom_line: str | None = None


# Bounded so a 100k-step real run cannot grow the history without limit;
# detectors only ever read the tail.
MAX_LOSS_HISTORY = 500


class TrainingLogParser:
    def __init__(self) -> None:
        self.progress = TrainingProgress()

    def feed_line(self, line: str) -> TrainingProgress:
        p = self.progress
        stripped = line.strip()

        if _OOM_RE.search(stripped):
            p.saw_oom = True
            p.oom_line = stripped

        step_match = _STEP_RE.search(stripped)
        if step_match:
            p.step = int(step_match.group(1))
            for key, value in _KV_RE.findall(stripped):
                self._apply_kv(p, step=p.step, key=key.lower(), value=value)

        ckpt = _CHECKPOINT_RE.search(stripped)
        if ckpt:
            p.last_checkpoint = ckpt.group(1)

        if _EVAL_RE.search(stripped):
            for key, value in _KV_RE.findall(stripped):
                try:
                    p.eval_metrics[key.lower()] = float(value)
                except ValueError:
                    continue
        return p

    @staticmethod
    def _apply_kv(p: TrainingProgress, step: int, key: str, value: str) -> None:
        if key == "loss":
            lowered = value.lower()
            if lowered in ("nan", "inf", "-inf"):
                p.saw_nan = True
                p.loss = math.nan if lowered == "nan" else math.inf
                return
            try:
                p.loss = float(value)
                p.loss_history.append((step, p.loss))
                if len(p.loss_history) > MAX_LOSS_HISTORY:
                    del p.loss_history[:-MAX_LOSS_HISTORY]
            except ValueError:
                pass
        elif key == "lr":
            try:
                p.lr = float(value)
            except ValueError:
                pass
        elif key == "epoch":
            try:
                p.epoch = float(value)
            except ValueError:
                pass
        elif key == "max_steps":
            try:
                p.max_steps = int(float(value))
            except ValueError:
                pass
