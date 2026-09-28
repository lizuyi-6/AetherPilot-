<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api/client";
import SystemHealth from "../components/system/SystemHealth.vue";
import { useSystemStore } from "../stores/system";
import { t } from "../i18n";
import type { ExperimentSummary, Scenario } from "../types";

const router = useRouter();
const system = useSystemStore();

const goal = ref(
  "Fine-tune Qwen3-4B on dataset/aether-v03. Target Macro-F1 >= 0.92. Complete within 6 hours. Keep VRAM under 100 GB."
);
const scenarios = ref<Scenario[]>([]);
const experiments = ref<ExperimentSummary[]>([]);
const busy = ref(false);
const error = ref<string | null>(null);
const selectedScenario = ref<string | null>(null);

onMounted(async () => {
  system.refresh();
  scenarios.value = await api.scenarios();
  experiments.value = await api.experiments();
});

function pickScenario(s: Scenario) {
  selectedScenario.value = s.id;
  goal.value = s.request.goal;
}

async function planAndRun() {
  busy.value = true;
  error.value = null;
  try {
    const scenario = scenarios.value.find((s) => s.id === selectedScenario.value);
    const body = scenario
      ? { ...scenario.request, goal: goal.value, name: `${scenario.request.name}-${Date.now() % 100000}` }
      : { name: `exp-${Date.now() % 100000}`, goal: goal.value, mode: "demo", demo: { step_delay: 0.2 } };
    const created = await api.createExperiment(body);
    await api.startExperiment(created.id);
    router.push(`/experiments/${created.id}`);
  } catch (e) {
    error.value = String(e);
  } finally {
    busy.value = false;
  }
}

function stateClass(state: string): string {
  if (state === "COMPLETED") return "ok";
  if (state === "FAILED" || state === "CANCELLED") return "crit";
  if (state === "CREATED") return "";
  return "accent";
}
</script>

<template>
  <div class="dashboard">
    <SystemHealth />

    <section class="hero panel">
      <div class="hero-top mono">
        <span class="tag accent" v-if="system.status?.gpu.available">{{ t("live") }}</span>
        <span class="tag warn" v-else>GPU UNAVAILABLE — DEMO MODE</span>
        <span class="host mono" v-if="system.status">
          {{ system.status.host.os }} {{ system.status.host.kernel }} · py {{ system.status.host.python }}
        </span>
      </div>
      <h2>{{ t("whatRun") }}</h2>
      <textarea v-model="goal" rows="4" class="mono" spellcheck="false" />
      <div class="scenario-row">
        <span class="scenario-label mono">{{ t("scenarios") }}</span>
        <button
          v-for="s in scenarios"
          :key="s.id"
          class="chip mono"
          :class="{ active: selectedScenario === s.id }"
          :title="s.description"
          @click="pickScenario(s)"
        >
          {{ s.id }} · {{ s.title }}
        </button>
      </div>
      <div class="actions">
        <button class="primary" :disabled="busy || !goal.trim()" @click="planAndRun">
          {{ busy ? "…" : t("planExperiment") }}
        </button>
        <span v-if="error" class="error mono">{{ error }}</span>
      </div>
    </section>

    <section class="panel">
      <div class="panel-title">{{ t("recentExperiments") }}</div>
      <table class="mono">
        <thead>
          <tr><th>ID</th><th>NAME</th><th>STATE</th><th>MODE</th><th>RECOVERIES</th><th>INTEGRITY</th><th>CREATED</th></tr>
        </thead>
        <tbody>
          <tr v-for="e in experiments" :key="e.id" @click="router.push(e.state === 'COMPLETED' ? `/experiments/${e.id}/result` : `/experiments/${e.id}`)">
            <td>{{ e.id.slice(0, 16) }}</td>
            <td>{{ e.name }}</td>
            <td><span class="tag" :class="stateClass(e.state)">{{ e.state }}</span></td>
            <td>{{ e.mode.toUpperCase() }}</td>
            <td>{{ e.recovery_attempts }}</td>
            <td>{{ e.integrity_status }}</td>
            <td>{{ new Date(e.created_at * 1000).toLocaleTimeString() }}</td>
          </tr>
          <tr v-if="!experiments.length"><td colspan="7" class="empty">no experiments yet</td></tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.dashboard { max-width: 1180px; margin: 0 auto; padding: 22px; display: flex; flex-direction: column; gap: 18px; }
.hero { padding: 26px 30px 22px; }
.hero-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.host { color: var(--text-faint); font-size: 11px; }
h2 { font-weight: 500; font-size: 22px; margin: 0 0 16px; color: var(--text); }
textarea {
  width: 100%; background: var(--bg); border: 1px solid var(--border-bright);
  color: var(--text); border-radius: var(--radius); padding: 12px 14px;
  font-size: 13px; line-height: 1.6; resize: vertical; outline: none;
}
textarea:focus { border-color: var(--accent); }
.scenario-row { display: flex; gap: 8px; align-items: center; margin: 14px 0; flex-wrap: wrap; }
.scenario-label { font-size: 10px; color: var(--text-faint); letter-spacing: 0.16em; }
.chip { font-size: 11px; padding: 5px 12px; }
.chip.active { border-color: var(--accent); color: var(--accent); }
.actions { display: flex; align-items: center; gap: 14px; }
.error { color: var(--crit); font-size: 11px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { text-align: left; padding: 8px 14px; color: var(--text-faint); font-size: 10px; letter-spacing: 0.14em; border-bottom: 1px solid var(--border); }
td { padding: 8px 14px; border-bottom: 1px solid var(--border); }
tbody tr { cursor: pointer; }
tbody tr:hover { background: var(--bg-raised); }
.empty { color: var(--text-faint); text-align: center; padding: 18px; }
</style>
