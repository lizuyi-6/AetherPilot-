"""E2E smoke test for the AetherPilot vertical slice (run against a live backend).

Covers acceptance items C–N: system status, experiment creation, contract
generation, training launch, telemetry, OOM incident + recovery + resume,
NaN incident + recovery + resume, completion, report + package.
"""

from __future__ import annotations

import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=30)

    status = client.get("/api/system/status").json()
    print(f"[C] system status: gpu_available={status['gpu']['available']} source={status['gpu']['source']}")

    skills = client.get("/api/skills").json()
    assert any(s["name"] == "hpc-experiment" for s in skills), "hpc-experiment skill not registered"
    print(f"[C+] skills: {[s['name'] for s in skills]}")

    create = client.post("/api/experiments", json={
        "name": "e2e-smoke",
        "goal": "Fine-tune Qwen3-4B on dataset/aether-v03. Target Macro-F1 >= 0.92. "
                "Complete within 6 hours. Keep VRAM under 100 GB.",
        "mode": "demo",
        "demo": {"inject_oom_at_step": 20, "inject_nan_at_step": 45, "step_delay": 0.15},
    })
    assert create.status_code == 200, create.text
    exp = create.json()
    exp_id = exp["id"]
    contract = exp["contract"]
    assert contract["metrics"]["macro_f1"]["target"] == 0.92, contract["metrics"]
    assert contract["goal"]["model"] == "Qwen3-4B"
    print(f"[D/E] experiment created: {exp_id}; contract metric macro_f1>=0.92; parsed model={contract['goal']['model']}")

    start = client.post(f"/api/experiments/{exp_id}/start")
    assert start.status_code == 200, start.text
    print("[F] training start requested")

    deadline = time.time() + 180
    final = None
    seen_states: list[str] = []
    while time.time() < deadline:
        detail = client.get(f"/api/experiments/{exp_id}").json()
        state = detail["state"]
        if not seen_states or seen_states[-1] != state:
            seen_states.append(state)
            print(f"    state → {state}")
        if state in ("COMPLETED", "FAILED", "CANCELLED"):
            final = detail
            break
        time.sleep(2)
    assert final is not None, "timed out waiting for terminal state"
    assert final["state"] == "COMPLETED", f"expected COMPLETED, got {final['state']}: {final.get('error')}"

    incidents = client.get(f"/api/experiments/{exp_id}/incidents").json()
    types = [i["type"] for i in incidents]
    assert "CUDA_OOM" in types and "NAN_LOSS" in types, types
    oom = next(i for i in incidents if i["type"] == "CUDA_OOM")
    patch = oom["recovery"]["config_patch"]
    assert patch["per_device_train_batch_size"] == 8, patch
    assert patch["gradient_accumulation_steps"] == 4, patch
    assert patch["gradient_checkpointing"] is True, patch
    nan = next(i for i in incidents if i["type"] == "NAN_LOSS")
    assert abs(nan["recovery"]["config_patch"]["learning_rate"] - 1.5e-5) < 1e-12
    assert nan["recovery"]["config_patch"]["max_grad_norm"] == 1.0
    print(f"[H-L] incidents: {types}; OOM patch batch 32→8 accum 1→4; NaN lr→1.5e-5 clip=1.0")

    metrics = final["final_metrics"]
    f1 = metrics["metrics"].get("macro_f1")
    assert isinstance(f1, float) and f1 >= 0.92, metrics
    assert final["best_checkpoint"], "no best checkpoint"
    print(f"[M] COMPLETED best={final['best_checkpoint']} macro_f1={f1} "
          f"integrity={final['integrity_status']} recoveries={final['recovery_attempts']}")

    report = client.get(f"/api/experiments/{exp_id}/report")
    assert report.status_code == 200 and "Experiment Report" in report.json()["markdown"]
    package = client.get(f"/api/experiments/{exp_id}/package")
    assert package.status_code == 200
    print(f"[N] report + reproducibility package at {package.json()['workspace']}")

    events = client.get(f"/api/experiments/{exp_id}/events").json()
    event_types = {e["type"] for e in events}
    for required in ("CONTRACT_CREATED", "PREFLIGHT_COMPLETED", "TRAINING_STARTED",
                     "INCIDENT_DETECTED", "RECOVERY_PLAN_CREATED", "CONFIG_PATCH_APPLIED",
                     "CHECKPOINT_ROLLBACK", "TRAINING_RESUMED", "RECOVERY_SUCCEEDED",
                     "EVALUATION_COMPLETED", "EXPERIMENT_COMPLETED"):
        assert required in event_types, f"missing event {required}"
    print(f"[G] events OK ({len(events)} events, all key types present)")
    print(f"    state path: {' → '.join(seen_states)}")
    print("\nE2E SMOKE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
