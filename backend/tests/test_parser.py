"""Training log parser tests."""

from __future__ import annotations

from app.training.parser import TrainingLogParser


def test_parses_step_loss_lr() -> None:
    p = TrainingLogParser()
    p.feed_line("STEP 12 loss=1.234 lr=0.00002 epoch=0.4")
    assert p.progress.step == 12
    assert p.progress.loss == 1.234
    assert p.progress.lr == 0.00002
    assert p.progress.epoch == 0.4


def test_detects_nan_and_inf() -> None:
    p = TrainingLogParser()
    p.feed_line("STEP 40 loss=nan lr=0.00002")
    assert p.progress.saw_nan
    p2 = TrainingLogParser()
    p2.feed_line("STEP 3 loss=inf")
    assert p2.progress.saw_nan


def test_detects_oom_text() -> None:
    p = TrainingLogParser()
    p.feed_line('RuntimeError: CUDA out of memory. Tried to allocate 3.8 GiB')
    assert p.progress.saw_oom
    assert "CUDA out of memory" in (p.progress.oom_line or "")


def test_checkpoint_tracking() -> None:
    p = TrainingLogParser()
    p.feed_line("CHECKPOINT SAVED checkpoint-30")
    assert p.progress.last_checkpoint == "checkpoint-30"


def test_eval_metrics() -> None:
    p = TrainingLogParser()
    p.feed_line("EVAL checkpoint=checkpoint-60 step=60 macro_f1=0.9437 samples=960")
    assert p.progress.eval_metrics["macro_f1"] == 0.9437


def test_loss_history_excludes_nan() -> None:
    p = TrainingLogParser()
    p.feed_line("STEP 1 loss=2.0")
    p.feed_line("STEP 2 loss=nan")
    assert p.progress.loss_history == [(1, 2.0)]
