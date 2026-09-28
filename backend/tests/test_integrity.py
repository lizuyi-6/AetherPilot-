"""Experiment integrity classification tests."""

from __future__ import annotations

from app.integrity.classifier import ChangeClass, classify_patch, effective_batch_size
from app.integrity.guard import IntegrityGuard, IntegrityStatus, render_config_diff

BASE = {
    "model": "Qwen3-4B",
    "dataset": "dataset/aether-v03",
    "per_device_train_batch_size": 32,
    "gradient_accumulation_steps": 1,
    "learning_rate": 2e-5,
    "max_grad_norm": 0.0,
    "gradient_checkpointing": False,
    "max_seq_length": 2048,
}


def test_oom_patch_preserves_semantics() -> None:
    patch = {"per_device_train_batch_size": 8, "gradient_accumulation_steps": 4, "gradient_checkpointing": True}
    cls, reasons = classify_patch(BASE, patch)
    assert cls is ChangeClass.SEMANTICS_PRESERVING
    assert any("effective batch size preserved" in r for r in reasons)


def test_effective_batch_change_is_semantic() -> None:
    patch = {"per_device_train_batch_size": 16}  # 16*1 != 32*1
    cls, _ = classify_patch(BASE, patch)
    assert cls is ChangeClass.SEMANTIC


def test_dataset_change_is_semantic() -> None:
    cls, _ = classify_patch(BASE, {"dataset": "dataset/other"})
    assert cls is ChangeClass.SEMANTIC


def test_model_change_is_semantic() -> None:
    cls, _ = classify_patch(BASE, {"model": "Qwen3-8B"})
    assert cls is ChangeClass.SEMANTIC


def test_lr_decrease_ok_increase_semantic() -> None:
    cls, _ = classify_patch(BASE, {"learning_rate": 1.5e-5})
    assert cls is ChangeClass.SEMANTICS_PRESERVING
    cls2, _ = classify_patch(BASE, {"learning_rate": 4e-5})
    assert cls2 is ChangeClass.SEMANTIC


def test_big_seq_len_change_is_semantic() -> None:
    cls, _ = classify_patch(BASE, {"max_seq_length": 512})
    assert cls is ChangeClass.SEMANTIC
    cls2, _ = classify_patch(BASE, {"max_seq_length": 1800})
    assert cls2 is ChangeClass.SEMANTICS_PRESERVING


def test_unknown_key_is_semantic() -> None:
    cls, _ = classify_patch(BASE, {"lora_rank": 16})
    assert cls is ChangeClass.SEMANTIC


def test_effective_batch_helper() -> None:
    assert effective_batch_size(BASE) == 32
    assert effective_batch_size({**BASE, "per_device_train_batch_size": 8, "gradient_accumulation_steps": 4}) == 32


def test_guard_tracks_and_summarizes() -> None:
    guard = IntegrityGuard()
    assert guard.status is IntegrityStatus.UNKNOWN
    guard.assess(BASE, {"per_device_train_batch_size": 8, "gradient_accumulation_steps": 4})
    assert guard.status is IntegrityStatus.PRESERVED
    guard.assess(BASE, {"dataset": "x"})
    assert guard.status is IntegrityStatus.MODIFIED
    summary = guard.summary()
    assert summary["automatic_changes"] == 1
    assert summary["approval_required"] == 1


def test_config_diff_renders_changes() -> None:
    diff = render_config_diff(BASE, {**BASE, "per_device_train_batch_size": 8})
    assert any(line.startswith("- per_device_train_batch_size: 32") for line in diff)
    assert any(line.startswith("+ per_device_train_batch_size: 8") for line in diff)
