# AetherPilot — Architecture

**Autonomous AI Experiment Operator** — an Agent that takes responsibility for a complete
HPC/AI experiment: plan → preflight → run → monitor → diagnose → recover → evaluate → package.

> From failed run to reproducible result.

---

## 1. Design Principles

```
LLM Reasoning  +  Deterministic Policy  +  Skill Runtime  +  Permission Gate  +  Observable Execution
```

- The LLM may *understand goals, explain logs, hypothesize root causes, summarize reports*.
- The LLM may **never** directly execute commands, edit configs, kill processes, or roll back
  checkpoints. All mutations pass through the **Policy Engine** and the **Experiment Contract**.
- No `LLM output → bash`. Ever.
- The system is fully functional without an LLM (rule-based reasoner fallback).
- No faked telemetry, no faked GPU state, no faked recovery. Demo Mode is explicitly labeled
  `DEMO WORKLOAD — Controlled Fault Injection`.

## 2. Repository Layout

```
aetherpilot/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI entry
│   │   ├── api/                    # REST + WebSocket routes
│   │   │   ├── system.py  experiments.py  skills.py  incidents.py  approvals.py  ws.py
│   │   ├── core/
│   │   │   ├── config.py           # Settings (env-driven)
│   │   │   ├── events.py           # Event bus + persistent event log
│   │   │   └── security.py         # CommandPolicy (READ_ONLY/SAFE_WRITE/PRIVILEGED/FORBIDDEN)
│   │   ├── agent/
│   │   │   ├── orchestrator.py     # Drives one experiment through the state machine
│   │   │   ├── state_machine.py    # Explicit states + transitions (persisted)
│   │   │   ├── planner.py          # Structured Plan (pydantic), LLM or rule-based
│   │   │   └── reasoning.py        # LLMProvider abstraction + RuleBasedReasoner
│   │   ├── contracts/
│   │   │   ├── models.py           # ExperimentContract (pydantic v2)
│   │   │   └── validator.py        # Contract validation
│   │   ├── skills/
│   │   │   ├── loader.py  registry.py  runtime.py
│   │   ├── runtime/
│   │   │   ├── command.py          # Safe subprocess (argv list, policy-checked)
│   │   │   └── filesystem.py       # Workspace jail, path resolution
│   │   ├── telemetry/
│   │   │   ├── collector.py        # background sampler -> JSONL
│   │   │   ├── gpu.py              # pynvml / nvidia-smi fallback / unavailable
│   │   │   └── system.py           # psutil
│   │   ├── incidents/
│   │   │   ├── models.py  detector.py  manager.py
│   │   ├── recovery/
│   │   │   ├── planner.py  executor.py  validator.py
│   │   ├── integrity/
│   │   │   ├── classifier.py       # semantics-preserving vs semantic changes
│   │   │   └── guard.py            # Experiment Integrity Guard
│   │   ├── training/
│   │   │   ├── launcher.py         # spawn training process
│   │   │   ├── parser.py           # training log parser (step/loss/lr)
│   │   │   └── checkpoint.py       # checkpoint discovery
│   │   ├── evaluation/
│   │   │   └── runner.py
│   │   ├── reproducibility/
│   │   │   └── packager.py
│   │   └── db/
│   │       ├── models.py  database.py
│   └── tests/
├── demo/
│   └── training_workload.py        # real python process, deterministic fault injection
├── skills/
│   └── hpc-experiment/             # SKILL.md, skill.yaml, policies/, detectors/, recovery/, schemas/, evals/
├── frontend/                       # Vue 3 + TS + Vite + Pinia + ECharts
├── scripts/                        # setup/dev/demo (.sh + .ps1)
├── architecture.md
├── progress.md
└── README.md
```

## 3. Agent State Machine

```
CREATED → CONTRACTING → PREFLIGHT → PLANNING → PREPARING → RUNNING ⇄ MONITORING
                                                              │
                                  ┌───────────────────────────┼──────────────────────┐
                                  ▼                           ▼                      ▼
                              INCIDENT                   EVALUATING               FAILED
                                  │                           │
                          DIAGNOSING                      PACKAGING                 │
                                  │                           │                      │
                       RECOVERY_PLANNING                  COMPLETED                  │
                                  │                                                    │
                    ┌─────────────┴──────────────┐                                   │
                    ▼                            ▼                                    │
            RECOVERING ──► RUNNING      WAITING_APPROVAL ──(approved)──► RECOVERING │
                    │                            │                                    │
                    └──────────► FAILED ◄──(rejected/cancelled)              CANCELLED
```

- States are persisted to SQLite after every transition; on backend restart an experiment can
  be resumed from its persisted state (recovery-in-flight is re-entered safely).
- `max_auto_recovery_attempts` (from the Contract) bounds the INCIDENT loop.

## 4. Core Data Models

### ExperimentContract (yaml-serializable, pydantic v2)
```yaml
experiment: { name: str }
goal:       { type: finetune|eval|custom, model: str, dataset: str|null, description: str }
constraints:{ max_vram_gb, max_duration_hours, max_disk_gb }
permissions:{ restart_training: bool, modify_training_config: bool,
              install_python_packages: bool, install_system_packages: ask|bool,
              modify_docker_daemon: ask|bool, kill_external_processes: false,
              delete_user_files: false }
metrics:    { macro_f1: { target: 0.92, operator: ">=" } }
reproducibility: { record_git_commit, record_environment, dataset_hash, model_hash, random_seed }
recovery:   { allow_checkpoint_rollback: bool, max_auto_recovery_attempts: int }
```

### Incident
```json
{ "id": "inc-001", "type": "CUDA_OOM|NAN_LOSS|PROCESS_CRASH|DISK_LOW|GPU_UNAVAILABLE",
  "severity": "low|medium|high|critical", "timestamp": "...",
  "evidence": ["..."], "root_cause": "...", "confidence": 0.94,
  "recommended_actions": [], "recovery_attempt": 1 }
```

### RecoveryPlan
```json
{ "incident_id": "...", "strategy": "oom_batch_reduction|nan_rollback",
  "config_patch": { "per_device_train_batch_size": 8, ... },
  "config_diff": ["- per_device_train_batch_size: 32", "+ per_device_train_batch_size: 8"],
  "checkpoint": "checkpoint-2000", "integrity": "PRESERVED",
  "requires_approval": false }
```

### Event
Every action emits an event: `SYSTEM_PREFLIGHT_STARTED, GPU_DETECTED, DATASET_HASHED,
EXPERIMENT_PLAN_CREATED, TRAINING_STARTED, CHECKPOINT_CREATED, INCIDENT_DETECTED,
DIAGNOSIS_STARTED, RECOVERY_PLAN_CREATED, CONFIG_PATCH_APPLIED, CHECKPOINT_ROLLBACK,
TRAINING_RESUMED, EVALUATION_STARTED, EXPERIMENT_COMPLETED, STATE_CHANGED, APPROVAL_* ...`
Events persist to SQLite **and** stream over WebSocket.

## 5. Skill Model

A **Skill** is professional capability: knowledge + decision logic + tool composition +
verification + safety policy. A **Tool** is one executable operation (`nvidia-smi`).

`skills/hpc-experiment/skill.yaml` declares capabilities, permissions, detectors, recovery
strategies and eval cases. The backend `SkillRegistry` loads skill packages; the
`SkillRuntime` invokes skill capabilities under the contract's permission gate.

HPCExperimentSkill capabilities:
`EnvironmentPreflight, ResourceEstimation, ExperimentPlanning, TrainingLauncher,
RuntimeMonitoring, FailureDiagnosis, SafeRecovery, CheckpointManagement, Evaluation,
ReproducibilityAudit`.

## 6. Security Model

- **CommandPolicy**: every command is classified `READ_ONLY | SAFE_WRITE | PRIVILEGED | FORBIDDEN`.
  `subprocess` is always invoked with an argv list, never `shell=True`.
- **Filesystem jail**: all writes confined to `data/experiments/<id>/`; read paths
  (model/dataset/repo) must be explicitly granted in the contract and are `resolve()`d and
  prefix-checked before use.
- **Permission gate**: contract permissions map to action classes; `ask` → `WAITING_APPROVAL`;
  `false` → hard deny.

## 7. Experiment Integrity

`IntegrityGuard` classifies a config patch as:
- **Semantics-preserving** (auto-allowed): `batch_size↓ × grad_accum↑` keeping effective batch,
  `gradient_checkpointing on`, LR reduction within bounds after instability, gradient clipping on.
- **Semantic** (requires human approval): dataset/model/loss/metric/split/label changes,
  large max-seq-len changes, goal changes.

UI shows `Automatic Changes / Semantic Changes / Approval Required` and integrity status
`PRESERVED / MODIFIED / UNKNOWN`.

## 8. API Surface

```
GET  /api/system/status
GET  /api/system/telemetry
GET  /api/skills
POST /api/experiments
GET  /api/experiments
GET  /api/experiments/{id}
POST /api/experiments/{id}/start
POST /api/experiments/{id}/stop
GET  /api/experiments/{id}/incidents
GET  /api/experiments/{id}/events
POST /api/experiments/{id}/approval/{approval_id}
GET  /api/experiments/{id}/report
WS   /ws/experiments/{id}
WS   /ws/system
```

## 9. Modes

- **REAL MODE**: real `nvidia-smi`, real training process, real telemetry (this dev machine:
  RTX 5070 Ti detected → LIVE). Docker optional, degrades gracefully.
- **DEMO MODE**: `demo/training_workload.py` is a *real* Python training process whose logs,
  checkpoints and failures are real; only the fault timing is controlled
  (`--inject-oom-at-step`, `--inject-nan-at-step`). UI labels it `DEMO WORKLOAD`.

## 10. LLM Integration

`LLMProvider` (OpenAI-compatible: `AETHER_LLM_BASE_URL / AETHER_LLM_API_KEY / AETHER_LLM_MODEL`)
handles goal parsing, incident explanation, root-cause hypothesis, report summarization.
`RuleBasedReasoner` provides the same structured outputs without any LLM. All safety-critical
decisions (detection, permission, integrity, config diff, checkpoint selection) are
deterministic regardless.
