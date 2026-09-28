# HPC Experiment Operator Skill

Gives an agent the professional capability of an HPC/ML infrastructure engineer:
run a GPU training experiment end-to-end, survive its failures, and prove what happened.

## What this skill knows (that a tool does not)

A tool can run `nvidia-smi`. This skill knows **when** memory matters, **what**
a VRAM spike during backward means, **how** to distinguish an OOM from a driver
fault, **which** config changes preserve the scientific meaning of the
experiment, and **how to prove** a recovery actually worked.

## Operating procedure

1. **Preflight** — never commit compute before verifying GPU, CUDA, disk, and
   dataset integrity. Hash the dataset; record the environment.
2. **Estimate** — VRAM/disk/runtime estimates carry risk levels. An estimate is
   not a guarantee; live telemetry refines it.
3. **Execute** — launch training as a supervised child process (argv list, no
   shell), stream and parse every log line.
4. **Detect** — deterministic signatures (OOM text, `loss=nan`, exit codes,
   disk thresholds). Detection never goes through an LLM.
5. **Diagnose** — gather evidence first (peak VRAM, step, LR, loss history,
   checkpoint state). Never patch blind.
6. **Recover safely** — only semantics-preserving changes run autonomously:
   - OOM: `batch_size /= 4` + `grad_accum *= 4` (effective batch preserved) +
     `gradient_checkpointing on`, resume from last checkpoint.
   - NaN: roll back to last stable checkpoint, `lr *= 0.75`,
     `max_grad_norm = 1.0`.
   Semantic changes (dataset/model/metric/objective/…) always require human
   approval.
7. **Verify** — a recovery counts only when the process is alive, the step
   advances past the failure point, loss is finite, and VRAM is within contract.
8. **Audit** — every change is logged (who/what/why/evidence/policy/timestamp)
   and the reproducibility package rebuilds the whole experiment.

## Boundaries

- Writes confined to the experiment workspace.
- No system mutation without explicit approval.
- No fabricated telemetry, no fake recovery: if the GPU is absent the skill
  reports `GPU UNAVAILABLE` and offers Demo Mode (controlled fault injection,
  clearly labeled).
