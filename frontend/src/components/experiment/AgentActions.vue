<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import type { AetherEvent } from "../../types";
import { t } from "../../i18n";

const props = defineProps<{ events: AetherEvent[] }>();

const feed = ref<HTMLDivElement | null>(null);

// Render only the tail — DOM nodes are the cost, not the array itself.
const MAX_RENDERED_ROWS = 200;

// Human-readable rendering of the agent's audit trail.
const LABELS: Record<string, string> = {
  EXPERIMENT_CREATED: "Experiment created",
  STATE_CHANGED: "State",
  SYSTEM_PREFLIGHT_STARTED: "Preflight started",
  GPU_DETECTED: "GPU detected",
  GPU_UNAVAILABLE: "GPU unavailable",
  CUDA_CHECKED: "CUDA checked",
  DOCKER_CHECKED: "Docker checked",
  STORAGE_CHECKED: "Storage checked",
  ENVIRONMENT_RECORDED: "Environment recorded",
  DATASET_HASHED: "Dataset hashed",
  RESOURCE_ESTIMATED: "Resources estimated",
  PREFLIGHT_COMPLETED: "Preflight complete",
  CONTRACT_CREATED: "Experiment contract created",
  EXPERIMENT_PLAN_CREATED: "Experiment plan created",
  CONFIG_GENERATED: "Training config generated",
  TRAINING_STARTED: "Training started",
  CHECKPOINT_CREATED: "Checkpoint saved",
  INCIDENT_DETECTED: "Incident detected",
  DIAGNOSIS_STARTED: "Diagnosing",
  DIAGNOSIS_COMPLETED: "Diagnosis complete",
  RECOVERY_PLAN_CREATED: "Recovery plan created",
  INTEGRITY_CHECKED: "Integrity checked",
  CONFIG_PATCH_APPLIED: "Config patch applied",
  CHECKPOINT_ROLLBACK: "Checkpoint rollback",
  TRAINING_RESUMED: "Training resumed",
  RECOVERY_SUCCEEDED: "Recovery verified",
  RECOVERY_FAILED: "Recovery failed",
  APPROVAL_REQUESTED: "Approval requested",
  APPROVAL_GRANTED: "Approval granted",
  APPROVAL_REJECTED: "Approval rejected",
  EVALUATION_STARTED: "Evaluation started",
  EVALUATION_COMPLETED: "Evaluation complete",
  EXPERIMENT_COMPLETED: "Experiment completed",
  EXPERIMENT_FAILED: "Experiment failed",
  EXPERIMENT_CANCELLED: "Experiment cancelled",
  PACKAGE_CREATED: "Reproducibility package created",
  AGENT_NOTE: "Note",
};

const rows = computed(() =>
  props.events
    .filter((e) => e.type !== "TRAINING_PROGRESS" && e.type !== "TELEMETRY_SAMPLE")
    .filter((e) => e.type !== "STATE_CHANGED" || ["FAILED", "COMPLETED", "CANCELLED"].includes(e.message))
    .slice(-MAX_RENDERED_ROWS)
    .map((e) => ({
      id: e.id,
      time: new Date(e.ts * 1000).toLocaleTimeString("en-GB", { hour12: false }),
      label: LABELS[e.type] ?? e.type,
      detail: e.message && e.message !== (LABELS[e.type] ?? "") ? e.message : "",
      severity: e.severity,
      hot: ["INCIDENT_DETECTED", "RECOVERY_PLAN_CREATED", "CONFIG_PATCH_APPLIED", "CHECKPOINT_ROLLBACK", "RECOVERY_SUCCEEDED", "APPROVAL_REQUESTED"].includes(e.type),
    }))
);

watch(
  () => props.events.length,
  async () => {
    await nextTick();
    if (feed.value) feed.value.scrollTop = feed.value.scrollHeight;
  }
);
</script>

<template>
  <div class="actions panel">
    <div class="panel-title">{{ t("agentActions") }}</div>
    <div class="feed" ref="feed">
      <div v-for="r in rows" :key="r.id" class="row" :class="[r.severity, { hot: r.hot }]">
        <span class="time mono">{{ r.time }}</span>
        <span class="label">{{ r.label }}</span>
        <span class="detail mono" :title="r.detail">{{ r.detail }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.actions { display: flex; flex-direction: column; min-height: 0; }
.feed { overflow-y: auto; max-height: 460px; padding: 6px 0; }
.row {
  display: grid; grid-template-columns: 62px 150px 1fr; gap: 10px;
  padding: 4px 14px; font-size: 12px; align-items: baseline;
}
.row .time { color: var(--text-faint); font-size: 10.5px; }
.row .label { color: var(--text-dim); }
.row .detail { color: var(--text-faint); font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row.hot .label { color: var(--text); }
.row.hot .detail { color: var(--text-dim); }
.row.error .label { color: var(--crit); }
.row.warning .label { color: var(--warn); }
</style>
