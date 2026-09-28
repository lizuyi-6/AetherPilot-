"""Experiment Integrity classification.

Decides whether a config change preserves the scientific meaning of the
experiment (semantics-preserving, auto-allowed) or changes what is being
measured (semantic change, requires human approval).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ChangeClass(StrEnum):
    SEMANTICS_PRESERVING = "semantics_preserving"
    SEMANTIC = "semantic"


# Keys that may never be changed automatically — they define the experiment itself.
SEMANTIC_KEYS = {
    "model",
    "model_name_or_path",
    "dataset",
    "dataset_path",
    "loss_function",
    "metric",
    "train_val_split",
    "labels",
    "task",
    "objective",
}

# Keys whose automatic modification is allowed only as a *decrease* or safe toggle
# after instability, and never change what the experiment measures.
RESOURCE_KEYS = {
    "per_device_train_batch_size",
    "gradient_accumulation_steps",
    "gradient_checkpointing",
    "max_grad_norm",
    "learning_rate",
    "dataloader_num_workers",
    "max_steps",
}

# Sequence length changes alter tokenization exposure — treat big changes as semantic.
SEQ_LEN_KEYS = {"max_seq_length", "max_length", "seq_len"}
SEQ_LEN_MAX_RATIO = 0.5  # automatic change allowed only within ±50%


def effective_batch_size(config: dict[str, Any]) -> float | None:
    batch = config.get("per_device_train_batch_size")
    accum = config.get("gradient_accumulation_steps", 1)
    if not isinstance(batch, (int, float)) or not isinstance(accum, (int, float)):
        return None
    return float(batch) * float(accum)


def classify_patch(
    original: dict[str, Any], patch: dict[str, Any]
) -> tuple[ChangeClass, list[str]]:
    """Classify a config patch. Returns (class, human-readable reasons)."""
    reasons: list[str] = []
    verdict = ChangeClass.SEMANTICS_PRESERVING

    for key, new_value in patch.items():
        old_value = original.get(key)

        if key in SEMANTIC_KEYS:
            verdict = ChangeClass.SEMANTIC
            reasons.append(f"'{key}' defines the experiment itself ({old_value!r} → {new_value!r})")
            continue

        if key in SEQ_LEN_KEYS:
            if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)) and old_value:
                ratio = abs(new_value - old_value) / old_value
                if ratio > SEQ_LEN_MAX_RATIO:
                    verdict = ChangeClass.SEMANTIC
                    reasons.append(
                        f"'{key}' changed by {ratio:.0%} (> {SEQ_LEN_MAX_RATIO:.0%} limit) "
                        f"({old_value} → {new_value})"
                    )
                else:
                    reasons.append(f"'{key}' within automatic bounds ({old_value} → {new_value})")
            continue

        if key not in RESOURCE_KEYS:
            verdict = ChangeClass.SEMANTIC
            reasons.append(f"'{key}' is not on the automatic-modification allowlist")
            continue

        reasons.append(f"'{key}' is a resource/stability knob ({old_value!r} → {new_value!r})")

    # Effective batch size preservation check when batch geometry changed.
    if {"per_device_train_batch_size", "gradient_accumulation_steps"} & set(patch):
        merged = {**original, **patch}
        old_eff = effective_batch_size(original)
        new_eff = effective_batch_size(merged)
        if old_eff is not None and new_eff is not None:
            if old_eff == new_eff:
                reasons.append(f"effective batch size preserved at {old_eff:g}")
            else:
                verdict = ChangeClass.SEMANTIC
                reasons.append(
                    f"effective batch size changed {old_eff:g} → {new_eff:g} — "
                    "this alters optimization dynamics"
                )

    # LR changes: automatic only as decrease (instability response), never increase.
    if "learning_rate" in patch:
        old_lr = original.get("learning_rate")
        new_lr = patch["learning_rate"]
        if isinstance(old_lr, (int, float)) and isinstance(new_lr, (int, float)):
            if new_lr > old_lr:
                verdict = ChangeClass.SEMANTIC
                reasons.append(f"learning rate increase {old_lr} → {new_lr} requires approval")
            else:
                reasons.append(f"learning rate reduced {old_lr} → {new_lr} (instability response)")

    return verdict, reasons
