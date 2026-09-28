"""Scenario D E2E: approval-gated recovery (contract forbids autonomous config changes)."""

from __future__ import annotations

import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=30)
    create = client.post("/api/experiments", json={
        "name": "e2e-approval-gated",
        "goal": "Fine-tune Qwen3-4B on dataset/aether-v03. Target Macro-F1 >= 0.92. Keep VRAM under 100 GB.",
        "mode": "demo",
        "demo": {"inject_oom_at_step": 20, "step_delay": 0.12},
        "contract_overrides": {"permissions": {"modify_training_config": False}},
    })
    assert create.status_code == 200, create.text
    exp_id = create.json()["id"]
    client.post(f"/api/experiments/{exp_id}/start")

    approved = False
    deadline = time.time() + 180
    state = ""
    while time.time() < deadline:
        detail = client.get(f"/api/experiments/{exp_id}").json()
        state = detail["state"]
        if state == "WAITING_APPROVAL" and not approved:
            approvals = client.get(f"/api/experiments/{exp_id}/approvals").json()
            pending = [a for a in approvals if a["status"] == "PENDING"]
            assert pending, "WAITING_APPROVAL without a pending approval row"
            resp = client.post(
                f"/api/experiments/{exp_id}/approval/{pending[0]['id']}", json={"decision": "approve"}
            )
            assert resp.status_code == 200, resp.text
            approved = True
            print(f"    approval {pending[0]['id']} GRANTED (human-in-the-loop path works)")
        if state in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        time.sleep(1.5)

    assert approved, "experiment never asked for approval"
    assert state == "COMPLETED", f"expected COMPLETED, got {state}"
    detail = client.get(f"/api/experiments/{exp_id}").json()
    incidents = client.get(f"/api/experiments/{exp_id}/incidents").json()
    assert [i["type"] for i in incidents] == ["CUDA_OOM"]
    assert detail["final_metrics"]["metrics"]["macro_f1"] >= 0.92
    print(f"    COMPLETED after human approval; f1={detail['final_metrics']['metrics']['macro_f1']}")
    print("SCENARIO D: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
