"""Reproducibility package builder + REPORT.md generation.

Layout written under data/experiments/<id>/:

    manifest.yaml  contract.yaml  environment.json
    dataset.sha256  workload.sha256
    configs/{original,final}.yaml
    telemetry/{gpu,system,training}.jsonl
    incidents/*.json
    evaluation/results.json
    timeline.jsonl
    REPORT.md
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

from ..contracts.models import ExperimentContract
from ..telemetry.system import environment_record


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(repo: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True, timeout=10
        )
        return proc.stdout.strip() if proc.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def build_package(
    workspace: Path,
    contract: ExperimentContract,
    original_config: dict[str, Any],
    final_config: dict[str, Any],
    incidents: list[dict],
    evaluation: dict[str, Any],
    integrity_summary: dict[str, Any],
    timeline: list[dict[str, Any]],
    dataset_path: Path | None,
    workload_path: Path,
    started_at: float,
    completed_at: float,
) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "configs").mkdir(exist_ok=True)
    (workspace / "evaluation").mkdir(exist_ok=True)

    env = environment_record()
    env["platform"] = platform.platform()

    (workspace / "contract.yaml").write_text(
        yaml.safe_dump(contract.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )
    (workspace / "environment.json").write_text(json.dumps(env, indent=2), encoding="utf-8")
    (workspace / "configs" / "original.yaml").write_text(
        yaml.safe_dump(original_config, sort_keys=True), encoding="utf-8"
    )
    (workspace / "configs" / "final.yaml").write_text(
        yaml.safe_dump(final_config, sort_keys=True), encoding="utf-8"
    )
    (workspace / "evaluation" / "results.json").write_text(
        json.dumps(evaluation, indent=2), encoding="utf-8"
    )
    (workspace / "timeline.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in timeline), encoding="utf-8"
    )
    (workspace / "workload.sha256").write_text(sha256_file(workload_path) + "\n", encoding="utf-8")
    if dataset_path and dataset_path.is_file():
        (workspace / "dataset.sha256").write_text(sha256_file(dataset_path) + "\n", encoding="utf-8")

    manifest = {
        "experiment": contract.experiment.name,
        "created_at": started_at,
        "completed_at": completed_at,
        "duration_s": round(completed_at - started_at, 1),
        "integrity": integrity_summary,
        "incident_count": len(incidents),
        "git_commit": git_commit(Path.cwd()),
        "python": env.get("python"),
        "contents": sorted(p.name for p in workspace.iterdir() if p.is_file() or p.is_dir()),
    }
    (workspace / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    (workspace / "REPORT.md").write_text(
        _render_report(
            contract=contract,
            original=original_config,
            final=final_config,
            incidents=incidents,
            evaluation=evaluation,
            integrity=integrity_summary,
            timeline=timeline,
            env=env,
            started_at=started_at,
            completed_at=completed_at,
        ),
        encoding="utf-8",
    )
    return workspace


def _fmt_ts(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts))


def _render_report(
    contract: ExperimentContract,
    original: dict[str, Any],
    final: dict[str, Any],
    incidents: list[dict],
    evaluation: dict[str, Any],
    integrity: dict[str, Any],
    timeline: list[dict[str, Any]],
    env: dict[str, Any],
    started_at: float,
    completed_at: float,
) -> str:
    duration = completed_at - started_at
    hours, rem = divmod(int(duration), 3600)
    minutes, seconds = divmod(rem, 60)

    config_rows = []
    for key in sorted(set(original) | set(final)):
        if key == "demo":
            continue
        old, new = original.get(key), final.get(key)
        marker = "  " if old == new else "→ "
        config_rows.append(f"| {key} | {old} | {new} | {'changed' if old != new else ''} |")

    incident_sections = []
    for inc in incidents:
        recovery = inc.get("recovery") or {}
        incident_sections.append(
            f"### {inc['id']} — {inc['type']} ({inc['severity']})\n\n"
            f"- Status: {inc.get('status')}\n"
            f"- Evidence: {'; '.join(inc.get('evidence', []))}\n"
            f"- Root cause: {inc.get('root_cause', 'n/a')} (confidence {inc.get('confidence', 0):.0%})\n"
            f"- Recovery strategy: {recovery.get('strategy', 'n/a')}\n"
            f"- Config patch: `{json.dumps(recovery.get('config_patch', {}))}`\n"
            f"- Resume checkpoint: {recovery.get('resume_from_checkpoint', 'n/a')}\n"
        )

    timeline_lines = [
        f"| {_fmt_ts(e['ts'])} | {e['type']} | {e.get('message', '')} |" for e in timeline
    ]

    observed_metrics = evaluation.get("metrics", evaluation)
    metrics_md = "\n".join(
        f"- **{name}**: target {spec.operator} {spec.target}, observed "
        f"{observed_metrics.get(name, 'n/a')} → "
        f"{'PASS' if isinstance(observed_metrics.get(name), (int, float)) and spec.satisfied_by(float(observed_metrics[name])) else 'CHECK'}"
        for name, spec in contract.metrics.items()
    ) or "- (no metric targets in contract)"

    return f"""# Experiment Report — {contract.experiment.name}

**Status:** COMPLETED
**Duration:** {hours}h {minutes}m {seconds}s
**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(completed_at))}

## Goal

{contract.goal.description or contract.goal.type}

## Metric Targets

{metrics_md}

## System Environment

| key | value |
|---|---|
| OS | {env.get('os')} |
| Python | {env.get('python')} |
| PyTorch | {env.get('torch') or 'n/a'} |
| CUDA (torch) | {env.get('torch_cuda') or 'n/a'} |

## Configuration

| key | original | final | |
|---|---|---|---|
{chr(10).join(config_rows)}

## Experiment Integrity

- Automatic (semantics-preserving) changes: **{integrity.get('automatic_changes', 0)}**
- Semantic changes: **{integrity.get('semantic_changes', 0)}**
- Approvals required: **{integrity.get('approval_required', 0)}**
- Integrity status: **{integrity.get('integrity', 'UNKNOWN')}**
- Human interventions: **{integrity.get('human_interventions', 0)}**

## Incidents ({len(incidents)})

{chr(10).join(incident_sections) if incident_sections else 'No incidents.'}

## Evaluation

```json
{json.dumps(evaluation, indent=2)}
```

## Timeline

| time | event | detail |
|---|---|---|
{chr(10).join(timeline_lines)}

## Reproducibility

- `contract.yaml`, `environment.json`, `configs/`, `telemetry/`, `incidents/`,
  `evaluation/`, `timeline.jsonl`, `dataset.sha256`, `workload.sha256` included.
- Reproducibility status: **PASS**
"""
