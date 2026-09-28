<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ state: string }>();

const STAGES = [
  { id: "01", label: "PREFLIGHT", states: ["CONTRACTING", "PREFLIGHT"] },
  { id: "02", label: "PLAN", states: ["PLANNING"] },
  { id: "03", label: "PREPARE", states: ["PREPARING"] },
  { id: "04", label: "TRAIN", states: ["RUNNING", "MONITORING", "INCIDENT", "DIAGNOSING", "RECOVERY_PLANNING", "RECOVERING", "WAITING_APPROVAL"] },
  { id: "05", label: "EVALUATE", states: ["EVALUATING"] },
  { id: "06", label: "PACKAGE", states: ["PACKAGING"] },
];

const ORDER = ["CREATED", "CONTRACTING", "PREFLIGHT", "PLANNING", "PREPARING", "RUNNING", "MONITORING",
  "INCIDENT", "DIAGNOSING", "RECOVERY_PLANNING", "RECOVERING", "WAITING_APPROVAL",
  "EVALUATING", "PACKAGING", "COMPLETED", "FAILED", "CANCELLED"];

const stageStatus = computed(() => {
  const currentIdx = ORDER.indexOf(props.state);
  return STAGES.map((stage) => {
    const indices = stage.states.map((s) => ORDER.indexOf(s));
    const maxIdx = Math.max(...indices);
    if (props.state === "COMPLETED") return { ...stage, status: "complete" };
    if (props.state === "FAILED" || props.state === "CANCELLED") {
      return { ...stage, status: currentIdx >= Math.min(...indices) && currentIdx <= maxIdx ? "failed" : maxIdx < currentIdx ? "complete" : "waiting" };
    }
    if (stage.states.includes(props.state)) {
      if (["INCIDENT", "DIAGNOSING", "RECOVERY_PLANNING", "RECOVERING"].includes(props.state))
        return { ...stage, status: "recovering" };
      if (props.state === "WAITING_APPROVAL") return { ...stage, status: "approval" };
      return { ...stage, status: "running" };
    }
    if (maxIdx < currentIdx) return { ...stage, status: "complete" };
    return { ...stage, status: "waiting" };
  });
});

const LABEL: Record<string, string> = {
  complete: "COMPLETE", running: "RUNNING", waiting: "WAITING",
  recovering: "RECOVERING", approval: "AWAITING APPROVAL", failed: "FAILED",
};
</script>

<template>
  <div class="mission panel">
    <div class="panel-title">MISSION</div>
    <div class="stages">
      <div v-for="s in stageStatus" :key="s.id" class="stage" :class="s.status">
        <span class="stage-id mono">{{ s.id }}</span>
        <span class="stage-label mono">{{ s.label }}</span>
        <span class="stage-status mono">{{ LABEL[s.status] }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stages { display: flex; flex-direction: column; }
.stage {
  display: grid; grid-template-columns: 34px 1fr auto; gap: 10px; align-items: center;
  padding: 10px 14px; border-bottom: 1px solid var(--border);
  font-size: 12px; color: var(--text-faint);
}
.stage:last-child { border-bottom: none; }
.stage-id { color: var(--text-faint); font-size: 11px; }
.stage-status { font-size: 10px; letter-spacing: 0.12em; }
.stage.complete { color: var(--text-dim); }
.stage.complete .stage-status { color: var(--ok); }
.stage.running { color: var(--text); background: rgba(76, 194, 255, 0.05); }
.stage.running .stage-status { color: var(--accent); }
.stage.recovering { color: var(--text); background: rgba(210, 153, 34, 0.06); }
.stage.recovering .stage-status { color: var(--warn); }
.stage.approval { color: var(--text); background: rgba(248, 81, 73, 0.06); }
.stage.approval .stage-status { color: var(--crit); }
.stage.failed .stage-status { color: var(--crit); }
</style>
