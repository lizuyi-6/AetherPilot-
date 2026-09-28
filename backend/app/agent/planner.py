"""Structured experiment planner.

Input: contract + system state + skill registry. Output: a typed Plan (pydantic)
— never free text to be reparsed.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    skill: str
    action: str
    reason: str


class Plan(BaseModel):
    goal: str
    training_config: dict[str, Any]
    steps: list[PlanStep] = Field(default_factory=list)


def build_plan(goal_description: str, parsed_goal: dict[str, Any], gpu_total_vram_gb: float | None) -> Plan:
    """Deterministic planning for the HPC experiment skill.

    Initial training config is derived from the parsed goal and (when known) the
    GPU budget; the demo workload carries its own pacing/fault-injection section.
    """
    max_steps = int(parsed_goal.get("max_steps", 60))
    training_config: dict[str, Any] = {
        "model": parsed_goal.get("model", "demo-small"),
        "dataset": parsed_goal.get("dataset", "demo://aether-v03"),
        "per_device_train_batch_size": 32,
        "gradient_accumulation_steps": 1,
        "learning_rate": 2e-5,
        "max_grad_norm": 0.0,
        "gradient_checkpointing": False,
        "max_seq_length": 2048,
        "max_steps": max_steps,
        "seed": 42,
    }
    steps = [
        PlanStep(skill="environment_preflight", action="inspect_system", reason="verify GPU/CUDA/disk before committing compute"),
        PlanStep(skill="resource_estimation", action="estimate", reason="confirm the config fits the contract budget"),
        PlanStep(skill="training_launcher", action="start", reason="launch the training process under supervision"),
        PlanStep(skill="runtime_monitoring", action="watch", reason="stream logs + telemetry until completion or incident"),
        PlanStep(skill="evaluation", action="evaluate_best_checkpoint", reason="compute target metric after training"),
        PlanStep(skill="reproducibility_audit", action="package", reason="produce the reproducibility package + report"),
    ]
    return Plan(goal=goal_description, training_config=training_config, steps=steps)
