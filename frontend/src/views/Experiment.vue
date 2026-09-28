<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { EChartsOption } from "echarts";
import type { Incident } from "../types";
import { api } from "../api/client";
import { useExperimentStore } from "../stores/experiment";
import { useSystemStore } from "../stores/system";
import { t } from "../i18n";
import MissionTimeline from "../components/experiment/MissionTimeline.vue";
import AgentActions from "../components/experiment/AgentActions.vue";
import IncidentCard from "../components/incident/IncidentCard.vue";
import ConfigDiff from "../components/incident/ConfigDiff.vue";
import BaseChart from "../components/charts/BaseChart.vue";

const route = useRoute();
const router = useRouter();
const store = useExperimentStore();
const system = useSystemStore();
const id = route.params.id as string;

onMounted(async () => {
  await store.load(id);
  store.connect(id);
  system.refresh();
});
onBeforeUnmount(() => store.disconnect());

const state = computed(() => store.detail?.state ?? "LOADING");
const isDemo = computed(() => store.detail?.mode === "demo");

const lossOption = computed<EChartsOption>(() => {
  const series = store.trainingSeries.filter((p) => p.loss !== null);
  return {
    grid: { top: 20, right: 14, bottom: 22, left: 44 },
    xAxis: { type: "value", name: "step", axisLabel: { color: "#74849a", fontSize: 10 }, splitLine: { show: false } },
    yAxis: { type: "value", name: "loss", axisLabel: { color: "#74849a", fontSize: 10 }, splitLine: { lineStyle: { color: "#1e2a38" } } },
    series: [{
      type: "line", showSymbol: false, smooth: true,
      data: series.map((p) => [p.step, p.loss]),
      lineStyle: { color: "#4cc2ff", width: 1.5 },
      areaStyle: { color: "rgba(76,194,255,0.08)" },
    }],
    backgroundColor: "transparent",
    textStyle: { fontFamily: "JetBrains Mono, Consolas, monospace" },
  };
});

const gpuOption = computed<EChartsOption>(() => {
  const samples = system.telemetry.slice(-120);
  return {
    grid: { top: 20, right: 14, bottom: 22, left: 44 },
    xAxis: { type: "category", show: false, data: samples.map((s) => s.ts) },
    yAxis: [
      { type: "value", name: "GPU %", max: 100, axisLabel: { color: "#74849a", fontSize: 10 }, splitLine: { lineStyle: { color: "#1e2a38" } } },
      { type: "value", name: "VRAM GB", axisLabel: { color: "#74849a", fontSize: 10 }, splitLine: { show: false } },
    ],
    series: [
      {
        name: "util", type: "line", showSymbol: false, yAxisIndex: 0,
        data: samples.map((s) => s.gpu.gpus[0]?.util_pct ?? 0),
        lineStyle: { color: "#3fb950", width: 1.2 },
      },
      {
        name: "vram", type: "line", showSymbol: false, yAxisIndex: 1,
        data: samples.map((s) => (s.gpu.gpus[0] ? s.gpu.gpus[0].mem_used_mb / 1024 : 0)),
        lineStyle: { color: "#d29922", width: 1.2 },
      },
    ],
    backgroundColor: "transparent",
    textStyle: { fontFamily: "JetBrains Mono, Consolas, monospace" },
    legend: { show: false },
  };
});

const liveDiff = computed(() => (store.lastRecoveryPlan?.payload?.diff as string[]) ?? []);
const liveStrategy = computed(() => {
  const plan = store.lastRecoveryPlan?.payload?.plan as { strategy?: string } | undefined;
  return plan?.strategy ?? "";
});
const integrityInfo = computed(() => store.integrity?.payload as Record<string, unknown> | null);
const gpu = computed(() => system.status?.gpu.gpus[0]);

const liveIncident = computed<Incident>(() => {
  const p = (store.activeIncident?.payload ?? {}) as Record<string, unknown>;
  return {
    id: (p.id as string) ?? "",
    ts: store.activeIncident?.ts ?? 0,
    type: (p.type as string) ?? "",
    severity: (p.severity as string) ?? "high",
    status: "OPEN",
    evidence: (p.evidence as string[]) ?? [],
    root_cause: (p.root_cause as string) ?? "",
    confidence: (p.confidence as number) ?? 0,
    recommended_actions: (p.recommended_actions as string[]) ?? [],
    recovery: {},
  };
});

async function stop() {
  await api.stopExperiment(id);
}
</script>

<template>
  <div class="experiment">
    <div class="exp-head">
      <div>
        <span class="exp-id mono">{{ id }}</span>
        <h1>{{ store.detail?.name ?? "…" }}</h1>
      </div>
      <div class="head-right">
        <span v-if="isDemo" class="tag warn">{{ t("demoWorkload") }}</span>
        <span class="tag" :class="state === 'COMPLETED' ? 'ok' : state === 'FAILED' ? 'crit' : 'accent'">{{ state }}</span>
        <button v-if="state === 'COMPLETED'" class="primary" @click="router.push(`/experiments/${id}/result`)">{{ t("viewReport") }}</button>
        <button v-if="!store.isTerminal" class="danger" @click="stop">{{ t("stop") }}</button>
      </div>
    </div>

    <div v-if="store.pendingApprovals.length" class="approval-banner panel">
      <div class="approval-text">
        <span class="tag crit">{{ t("approvalRequired") }}</span>
        <span class="reason">{{ store.pendingApprovals[0].reason }}</span>
      </div>
      <div class="approval-actions">
        <button class="ok" @click="store.decide(store.pendingApprovals[0].id, 'approve')">{{ t("approve") }}</button>
        <button class="danger" @click="store.decide(store.pendingApprovals[0].id, 'reject')">{{ t("reject") }}</button>
      </div>
    </div>

    <div class="grid">
      <aside class="left">
        <MissionTimeline :state="state" />
        <div class="panel integrity-panel">
          <div class="panel-title">{{ t("integrity") }}</div>
          <div class="integrity-body mono">
            <div class="irow"><span>Automatic Changes</span><b>{{ store.detail?.auto_changes ?? 0 }}</b></div>
            <div class="irow"><span>Semantic Changes</span><b>{{ store.detail?.semantic_changes ?? 0 }}</b></div>
            <div class="irow"><span>Approval Required</span><b>{{ integrityInfo?.approval_required ?? 0 }}</b></div>
            <div class="irow big">
              <span>Integrity</span>
              <b :class="store.detail?.integrity_status === 'PRESERVED' ? 'ok-text' : store.detail?.integrity_status === 'MODIFIED' ? 'warn-text' : ''">
                {{ store.detail?.integrity_status ?? "UNKNOWN" }}
              </b>
            </div>
          </div>
        </div>
      </aside>

      <section class="center">
        <div class="metrics-row">
          <div class="metric panel"><div class="m-label mono">STEP</div>
            <div class="m-value mono">{{ store.progress.step }}<span class="m-dim"> / {{ store.progress.maxSteps || "…" }}</span></div></div>
          <div class="metric panel"><div class="m-label mono">LOSS</div>
            <div class="m-value mono">{{ store.progress.loss?.toFixed(4) ?? "—" }}</div></div>
          <div class="metric panel"><div class="m-label mono">GPU</div>
            <div class="m-value mono">{{ gpu ? gpu.util_pct.toFixed(0) + "%" : "N/A" }}</div></div>
          <div class="metric panel"><div class="m-label mono">VRAM</div>
            <div class="m-value mono">{{ gpu ? (gpu.mem_used_mb / 1024).toFixed(1) + " GB" : "N/A" }}</div></div>
        </div>

        <div class="panel chart-panel">
          <div class="panel-title">TRAINING LOSS <span class="mono chart-tag">live</span></div>
          <BaseChart :option="lossOption" height="170px" />
        </div>
        <div class="panel chart-panel">
          <div class="panel-title">GPU TELEMETRY <span class="mono chart-tag">{{ gpu ? "LIVE" : "N/A" }}</span></div>
          <BaseChart :option="gpuOption" height="170px" />
        </div>

        <div v-if="store.activeIncident" class="live-incident">
          <IncidentCard :incident="liveIncident" live />
          <div v-if="store.lastRecoveryPlan" class="panel recovery-live">
            <div class="panel-title">RECOVERY — {{ liveStrategy }}</div>
            <ConfigDiff :diff="liveDiff" />
            <div class="recovery-status mono">{{ state === "RECOVERING" ? "APPLYING PATCH… RECOVERING…" : state }}</div>
          </div>
        </div>
      </section>

      <aside class="right">
        <AgentActions :events="store.events" />
        <div class="panel incidents-panel" v-if="store.incidents.length">
          <div class="panel-title">{{ t("incidents") }} ({{ store.incidents.length }})</div>
          <IncidentCard v-for="inc in store.incidents" :key="inc.id" :incident="inc" />
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.experiment { max-width: 1560px; margin: 0 auto; padding: 18px 22px; display: flex; flex-direction: column; gap: 14px; }
.exp-head { display: flex; justify-content: space-between; align-items: flex-end; }
.exp-id { color: var(--text-faint); font-size: 11px; }
h1 { margin: 2px 0 0; font-size: 20px; font-weight: 500; }
.head-right { display: flex; gap: 10px; align-items: center; }
.approval-banner {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; border-color: var(--crit); gap: 18px;
}
.approval-text { display: flex; gap: 14px; align-items: center; }
.reason { font-size: 12.5px; color: var(--text-dim); }
.approval-actions { display: flex; gap: 10px; }
.grid { display: grid; grid-template-columns: 250px minmax(0, 1fr) 400px; gap: 14px; align-items: start; }
.left, .right { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.center { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.metrics-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.metric { padding: 10px 14px; }
.m-label { font-size: 10px; letter-spacing: 0.16em; color: var(--text-faint); }
.m-value { font-size: 22px; margin-top: 4px; }
.m-dim { font-size: 13px; color: var(--text-faint); }
.chart-tag { font-size: 9px; color: var(--ok); letter-spacing: 0.2em; }
.integrity-body { padding: 10px 14px; display: flex; flex-direction: column; gap: 7px; font-size: 11.5px; }
.irow { display: flex; justify-content: space-between; color: var(--text-dim); }
.irow b { font-weight: 500; color: var(--text); }
.irow.big { border-top: 1px solid var(--border); padding-top: 8px; margin-top: 2px; }
.ok-text { color: var(--ok); }
.warn-text { color: var(--warn); }
.live-incident { display: flex; flex-direction: column; gap: 12px; }
.recovery-status { padding: 10px 14px; font-size: 11px; letter-spacing: 0.14em; color: var(--warn); }
.incidents-panel { display: flex; flex-direction: column; }
.incidents-panel .panel-title { flex: 0 0 auto; }
.incidents-panel > :not(.panel-title) { margin: 10px 10px 0; }
.incidents-panel > :last-child { margin-bottom: 10px; }
</style>
