# AetherPilot — Progress

## DONE
- PHASE 0: Repo (empty) + environment probe — Python 3.12 venv via uv (MSYS2 Python 3.14
  lacks ensurepip), Node 24, NVIDIA RTX 5070 Ti live via pynvml, Docker daemon down
  (degrades honestly).
- PHASE 1: architecture.md (models, modules, state machine, API, events, security).
- PHASE 2-4: Backend skeleton — config/db/events/security, GPU+system telemetry,
  ExperimentContract + validator, persisted state machine.
- PHASE 5-9: Demo workload (real process, config-causal fault injection), launcher +
  log parser, incident detectors (OOM/NaN/crash/disk), recovery planner/executor/
  validator, checkpoint discovery + rollback resume.
- PHASE 10: Reproducibility package + REPORT.md.
- PHASE 11-12: Frontend (Dashboard/Experiment/Result/Skills, ECharts, WebSocket live
  events + telemetry, i18n scaffold en/zh). Type-check + production build pass.
- PHASE 13-14: skills/hpc-experiment package (SKILL.md, skill.yaml, policies, schemas,
  evals) + LLMProvider abstraction with rule-based fallback.
- PHASE 15: 65 unit tests PASS (contract, command policy, path jail, integrity, parser,
  checkpoints, detectors, recovery, state machine, reasoner).
- PHASE 16 (partial): E2E smoke (OOM+NaN full slice) PASS; approval-gated scenario D PASS;
  browser walkthrough of dashboard → scenario C → incident → recovery → result page PASS.

## IN PROGRESS
- (none)

## BLOCKED
- (none)

## NEXT
- P1 roadmap: HuggingFace Trainer adapter, Docker runner isolation.
- Optional polish: ECharts bundle code-splitting.

## Verification Log (final, all green)
- pytest: 65 passed (contract, command policy, path jail, integrity, parser,
  checkpoints, detectors, recovery, state machine, reasoner).
- e2e_smoke (fixed backend): COMPLETED, macro_f1=0.9323 ≥ 0.92 target, 2 autonomous
  recoveries (OOM batch 32→8/accum 1→4/grad-ckpt on; NaN rollback lr→1.5e-5 clip=1.0),
  integrity PRESERVED, 155 events, checkpoint-event dedup confirmed.
- e2e_approval: WAITING_APPROVAL → human approve → COMPLETED.
- vue-tsc clean, vite build clean.
- Browser walkthrough: dashboard (live GPU/CPU/RAM/disk/CUDA/Docker), scenario B/C runs,
  incident cards with evidence + config diff, result page + rendered REPORT.md.
  Screenshots archived in docs/screenshots/.
- Report fix verified: metric target line shows observed 0.9323 → PASS.
