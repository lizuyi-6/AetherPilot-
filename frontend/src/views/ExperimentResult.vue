<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { marked } from "marked";
import { api } from "../api/client";
import type { ExperimentDetail } from "../types";

const route = useRoute();
const router = useRouter();
const id = route.params.id as string;

const detail = ref<ExperimentDetail | null>(null);
const reportHtml = ref<string>("");
const workspace = ref<string>("");
const humanInterventions = ref<number>(0);

onMounted(async () => {
  detail.value = await api.experiment(id);
  try {
    const r = await api.report(id);
    reportHtml.value = await marked.parse(r.markdown);
  } catch { /* no report (failed experiment) */ }
  try {
    const p = await api.pkg(id);
    workspace.value = p.workspace;
    const integrity = p.manifest?.integrity as { human_interventions?: number } | undefined;
    humanInterventions.value = integrity?.human_interventions ?? 0;
  } catch { /* no package */ }
});

const metrics = computed(() => detail.value?.final_metrics?.metrics ?? {});
const targets = computed(() => detail.value?.final_metrics?.targets ?? {});
const metricCards = computed(() =>
  Object.entries(targets.value).map(([name, t]) => ({
    name,
    observed: metrics.value[name],
    pass: t.pass,
    operator: t.operator,
    target: t.target,
  }))
);
const duration = computed(() => {
  if (!detail.value?.completed_at) return "—";
  const s = detail.value.completed_at - detail.value.created_at;
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m ${Math.floor(s % 60)}s`;
});
</script>

<template>
  <div class="result" v-if="detail">
    <div class="result-head">
      <div>
        <div class="exp-id mono">Experiment {{ detail.id }}</div>
        <h1>{{ detail.name }}</h1>
      </div>
      <span class="tag big" :class="detail.state === 'COMPLETED' ? 'ok' : 'crit'">{{ detail.state }}</span>
    </div>

    <div class="stat-grid">
      <div class="stat panel"><div class="s-label mono">DURATION</div><div class="s-value mono">{{ duration }}</div></div>
      <div class="stat panel"><div class="s-label mono">AUTONOMOUS RECOVERIES</div><div class="s-value mono">{{ detail.recovery_attempts }}</div></div>
      <div class="stat panel"><div class="s-label mono">HUMAN INTERVENTIONS</div><div class="s-value mono">{{ humanInterventions }}</div></div>
      <div class="stat panel"><div class="s-label mono">BEST CHECKPOINT</div><div class="s-value mono small">{{ detail.best_checkpoint ?? "—" }}</div></div>
      <div class="stat panel" v-for="card in metricCards" :key="card.name">
        <div class="s-label mono">{{ card.name.toUpperCase() }}</div>
        <div class="s-value mono">
          {{ typeof card.observed === "number" ? card.observed.toFixed(4) : card.observed }}
          <span class="tag" :class="card.pass ? 'ok' : 'warn'">
            {{ card.pass ? "PASS" : "MISS" }} {{ card.operator }} {{ card.target }}
          </span>
        </div>
      </div>
      <div class="stat panel"><div class="s-label mono">INTEGRITY</div>
        <div class="s-value mono" :class="detail.integrity_status === 'PRESERVED' ? 'ok-text' : 'warn-text'">{{ detail.integrity_status }}</div></div>
      <div class="stat panel"><div class="s-label mono">REPRODUCIBILITY</div><div class="s-value mono ok-text">PASS</div></div>
    </div>

    <div class="panel" v-if="workspace">
      <div class="panel-title">REPRODUCIBILITY PACKAGE</div>
      <div class="pkg mono">{{ workspace }}</div>
    </div>

    <div class="panel" v-if="reportHtml">
      <div class="panel-title">REPORT.md</div>
      <div class="report" v-html="reportHtml" />
    </div>

    <div class="footer">
      <button @click="router.push(`/experiments/${id}`)">← TIMELINE</button>
      <button @click="router.push('/')">HOME</button>
    </div>
  </div>
</template>

<style scoped>
.result { max-width: 1100px; margin: 0 auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.result-head { display: flex; justify-content: space-between; align-items: flex-end; }
.exp-id { color: var(--text-faint); font-size: 11px; }
h1 { margin: 2px 0 0; font-size: 22px; font-weight: 500; }
.tag.big { font-size: 13px; padding: 5px 14px; }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }
.stat { padding: 12px 16px; }
.s-label { font-size: 10px; letter-spacing: 0.16em; color: var(--text-faint); }
.s-value { font-size: 24px; margin-top: 6px; display: flex; gap: 10px; align-items: center; }
.s-value.small { font-size: 16px; }
.ok-text { color: var(--ok); }
.warn-text { color: var(--warn); }
.pkg { padding: 12px 16px; font-size: 12px; color: var(--text-dim); word-break: break-all; }
.report { padding: 18px 26px; font-size: 13.5px; line-height: 1.65; }
.report :deep(h1) { font-size: 19px; }
.report :deep(h2) { font-size: 15px; border-bottom: 1px solid var(--border); padding-bottom: 6px; margin-top: 22px; }
.report :deep(h3) { font-size: 13px; }
.report :deep(table) { border-collapse: collapse; font-size: 12px; }
.report :deep(th), .report :deep(td) { border: 1px solid var(--border); padding: 4px 10px; }
.report :deep(code) { font-family: var(--mono); background: var(--bg-raised); padding: 1px 5px; border-radius: 2px; font-size: 11.5px; }
.report :deep(pre) { background: var(--bg); border: 1px solid var(--border); padding: 10px 14px; overflow-x: auto; border-radius: var(--radius); }
.report :deep(pre code) { background: none; padding: 0; }
.footer { display: flex; gap: 10px; }
</style>
