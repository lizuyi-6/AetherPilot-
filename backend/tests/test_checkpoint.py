"""Checkpoint discovery tests."""

from __future__ import annotations

import json

from app.training.checkpoint import last_stable_checkpoint, latest_checkpoint, list_checkpoints


def _make_ckpt(root, step: int, loss: float | None = 1.0) -> None:
    d = root / f"checkpoint-{step}"
    d.mkdir(parents=True)
    (d / "meta.json").write_text(json.dumps({"step": step, "loss": loss}))


def test_list_sorted_by_step(tmp_path) -> None:
    for step in (30, 10, 20):
        _make_ckpt(tmp_path, step)
    ckpts = list_checkpoints(tmp_path)
    assert [c.step for c in ckpts] == [10, 20, 30]


def test_latest_before_step(tmp_path) -> None:
    for step in (10, 20, 30):
        _make_ckpt(tmp_path, step)
    assert latest_checkpoint(tmp_path, before_step=25).step == 20
    assert latest_checkpoint(tmp_path, before_step=10) is None


def test_last_stable_skips_nan(tmp_path) -> None:
    _make_ckpt(tmp_path, 10, loss=1.5)
    _make_ckpt(tmp_path, 20, loss=float("nan"))
    _make_ckpt(tmp_path, 30, loss=0.9)
    stable = last_stable_checkpoint(tmp_path)
    assert stable.step == 30
    assert last_stable_checkpoint(tmp_path, before_step=25).step == 10


def test_missing_dir(tmp_path) -> None:
    assert list_checkpoints(tmp_path / "nope") == []
    assert latest_checkpoint(tmp_path / "nope") is None
