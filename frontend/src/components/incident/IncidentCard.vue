<script setup lang="ts">
import { computed } from "vue";
import type { Incident } from "../../types";

const props = defineProps<{ incident: Incident; live?: boolean }>();

const TITLE: Record<string, string> = {
  CUDA_OOM: "CUDA OUT OF MEMORY",
  NAN_LOSS: "LOSS DIVERGED (NaN/Inf)",
  PROCESS_CRASH: "TRAINING PROCESS CRASH",
  DISK_LOW: "DISK SPACE LOW",
  GPU_UNAVAILABLE: "GPU UNAVAILABLE",
};

const recoveryDiff = computed(() => {
  const patch = props.incident.recovery?.config_patch ?? {};
  return Object.entries(patch).map(([k, v]) => ({ key: k, value: v }));
});
</script>

<template>
  <div class="incident panel" :class="{ live }">
    <div class="head">
      <span class="tag crit">INCIDENT DETECTED</span>
      <span class="title mono">{{ TITLE[incident.type] ?? incident.type }}</span>
      <span class="status tag" :class="incident.status === 'RESOLVED' ? 'ok' : 'warn'">{{ incident.status }}</span>
    </div>

    <div class="section">
      <div class="section-title mono">EVIDENCE</div>
      <ul class="evidence mono">
        <li v-for="(e, i) in incident.evidence" :key="i">{{ e }}</li>
      </ul>
    </div>

    <div class="section">
      <div class="section-title mono">ROOT CAUSE <span class="conf">confidence {{ (incident.confidence * 100).toFixed(0) }}%</span></div>
      <p class="cause">{{ incident.root_cause }}</p>
    </div>

    <div class="section" v-if="incident.recovery?.strategy">
      <div class="section-title mono">RECOVERY PLAN — {{ incident.recovery.strategy }}</div>
      <div class="patch" v-if="recoveryDiff.length">
        <div v-for="item in recoveryDiff" :key="item.key" class="patch-row mono">
          <span class="pk">{{ item.key }}</span>
          <span class="pv">→ {{ item.value }}</span>
        </div>
      </div>
      <div class="rollback mono" v-if="incident.recovery?.resume_from_checkpoint">
        resume from <b>{{ incident.recovery.resume_from_checkpoint }}</b>
      </div>
      <div class="integrity mono" v-if="incident.recovery?.integrity">
        integrity: <span :class="incident.recovery.integrity === 'semantics_preserving' ? 'ok-text' : 'warn-text'">
          {{ incident.recovery.integrity === "semantics_preserving" ? "PRESERVED" : "MODIFIED" }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.incident { border-color: rgba(248, 81, 73, 0.35); }
.incident.live { box-shadow: 0 0 0 1px rgba(248, 81, 73, 0.25); }
.head { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-bottom: 1px solid var(--border); }
.title { font-size: 13px; letter-spacing: 0.08em; flex: 1; }
.section { padding: 10px 14px; border-bottom: 1px solid var(--border); }
.section:last-child { border-bottom: none; }
.section-title { font-size: 10px; letter-spacing: 0.16em; color: var(--text-faint); margin-bottom: 6px; }
.conf { color: var(--text-faint); letter-spacing: 0; text-transform: none; margin-left: 8px; }
.evidence { margin: 0; padding-left: 16px; font-size: 11.5px; color: var(--text-dim); }
.evidence li { margin: 2px 0; word-break: break-all; }
.cause { margin: 0; font-size: 12.5px; color: var(--text); line-height: 1.55; }
.patch { display: flex; flex-direction: column; gap: 3px; font-size: 12px; }
.patch-row { display: grid; grid-template-columns: 240px 1fr; gap: 8px; }
.pk { color: var(--text-dim); }
.pv { color: var(--warn); }
.rollback { margin-top: 8px; font-size: 11.5px; color: var(--text-dim); }
.rollback b { color: var(--accent); font-weight: 500; }
.integrity { margin-top: 6px; font-size: 11px; color: var(--text-dim); }
.ok-text { color: var(--ok); }
.warn-text { color: var(--warn); }
</style>
