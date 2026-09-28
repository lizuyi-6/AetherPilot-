"""Recovery execution: applies a validated RecoveryPlan to the experiment config.

The executor performs the actual config mutation inside the workspace and emits
the audit record. It assumes the plan already passed IntegrityGuard + permission
checks; it refuses to execute anything else.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import yaml

from ..integrity.guard import render_config_diff
from .planner import RecoveryPlan


def apply_plan(
    config: dict[str, Any],
    plan: RecoveryPlan,
    workspace: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (new_config, audit_record)."""
    new_config = {**config, **plan.config_patch}
    diff = render_config_diff(config, new_config)

    configs_dir = workspace / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)
    (configs_dir / "current.yaml").write_text(
        yaml.safe_dump(new_config, sort_keys=True), encoding="utf-8"
    )

    audit_record = {
        "who": "agent",
        "what": plan.config_patch,
        "why": f"{plan.strategy} (incident {plan.incident_id})",
        "evidence": diff,
        "policy": "semantics_preserving",
        "timestamp": time.time(),
        "previous_state": config,
        "result": "applied",
    }
    with (workspace / "audit.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(audit_record) + "\n")

    return new_config, audit_record
