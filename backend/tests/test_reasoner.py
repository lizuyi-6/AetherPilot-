"""Rule-based goal parsing tests (the always-available reasoner)."""

from __future__ import annotations

from app.agent.reasoning import RuleBasedReasoner


def test_parses_full_goal() -> None:
    r = RuleBasedReasoner()
    parsed = r.parse_goal(
        "Fine-tune Qwen3-4B on dataset/aether-v03. Target Macro-F1 >= 0.92. "
        "Complete within 6 hours. Keep VRAM under 100 GB."
    )
    assert parsed["model"] == "Qwen3-4B"
    assert parsed["type"] == "finetune"
    assert parsed["dataset"] == "dataset/aether-v03"
    assert parsed["metric"] == {"name": "macro_f1", "operator": ">=", "target": 0.92}
    assert parsed["max_duration_hours"] == 6.0
    assert parsed["max_vram_gb"] == 100.0


def test_minimal_goal_defaults() -> None:
    r = RuleBasedReasoner()
    parsed = r.parse_goal("train something")
    assert parsed["type"] == "finetune"
    assert "model" not in parsed
    assert "metric" not in parsed


def test_incident_explanations_cover_all_types() -> None:
    r = RuleBasedReasoner()
    for t in ("CUDA_OOM", "NAN_LOSS", "PROCESS_CRASH", "DISK_LOW", "GPU_UNAVAILABLE"):
        text = r.explain_incident(t, ["evidence-1"])
        assert "evidence-1" in text
