<script setup lang="ts">
import { computed } from "vue";
import { useSystemStore } from "../../stores/system";
import { t } from "../../i18n";

const system = useSystemStore();

const items = computed(() => {
  const s = system.status;
  if (!s) return [];
  // Prefer the live WS telemetry sample; fall back to the status snapshot.
  const live = system.telemetry[system.telemetry.length - 1] ?? null;
  const gpu = live?.gpu.gpus[0] ?? s.gpu.gpus[0];
  const cpu = live?.cpu_pct ?? s.cpu_pct;
  const ramUsed = live?.ram_used_gb ?? s.ram.used_gb;
  const diskFree = live?.disk_free_gb ?? s.disk.free_gb;
  const dockerOk = s.docker.available;
  return [
    {
      key: "GPU",
      value: gpu ? gpu.name.replace("NVIDIA ", "") : "UNAVAILABLE",
      sub: gpu ? `${(gpu.mem_total_mb / 1024).toFixed(0)} GB` : "",
      status: gpu ? "ok" : "crit",
    },
    {
      key: "VRAM",
      value: gpu ? `${(gpu.mem_used_mb / 1024).toFixed(1)} / ${(gpu.mem_total_mb / 1024).toFixed(0)} GB` : "—",
      sub: gpu ? `${gpu.util_pct.toFixed(0)}% util` : "",
      status: gpu ? "ok" : "crit",
    },
    { key: "CPU", value: `${cpu.toFixed(0)}%`, sub: `${s.host.cpu_count} cores`, status: "ok" },
    {
      key: "RAM",
      value: `${ramUsed.toFixed(0)} / ${s.ram.total_gb.toFixed(0)} GB`,
      sub: "", status: "ok",
    },
    {
      key: "DISK",
      value: `${diskFree.toFixed(0)} GB free`,
      sub: `of ${s.disk.total_gb.toFixed(0)} GB`,
      status: diskFree > 20 ? "ok" : diskFree > 5 ? "warn" : "crit",
    },
    {
      key: "CUDA",
      value: s.gpu.cuda ? `driver ${s.gpu.cuda}` : "—",
      sub: s.gpu.driver ? `drv ${s.gpu.driver}` : "",
      status: s.gpu.available ? "ok" : "crit",
    },
    {
      key: "DOCKER",
      value: dockerOk ? "Ready" : "Unavailable",
      sub: dockerOk ? (s.docker.nvidia_runtime ? "nvidia runtime" : "no nvidia runtime") : "daemon down",
      status: dockerOk ? "ok" : "warn",
    },
  ];
});

const overall = computed(() => {
  const s = system.status;
  if (!s) return { cls: "warn", label: "…" };
  if (!s.gpu.available) return { cls: "warn", label: t("degraded") };
  return { cls: "ok", label: t("healthy") };
});
</script>

<template>
  <div class="health panel">
    <div class="health-head">
      <span>{{ t("systemHealth") }}</span>
      <span class="tag" :class="overall.cls">{{ overall.label }}</span>
    </div>
    <div class="health-grid">
      <div v-for="item in items" :key="item.key" class="cell">
        <div class="cell-key mono">{{ item.key }}</div>
        <div class="cell-value mono">
          <span class="status-dot" :class="item.status" />{{ item.value }}
        </div>
        <div class="cell-sub mono">{{ item.sub }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.health { padding: 0; }
.health-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; border-bottom: 1px solid var(--border);
  font-family: var(--mono); font-size: 11px; letter-spacing: 0.18em; color: var(--text-dim);
}
.health-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
}
.cell { padding: 10px 14px; border-right: 1px solid var(--border); }
.cell:last-child { border-right: none; }
.cell-key { font-size: 10px; color: var(--text-faint); letter-spacing: 0.16em; }
.cell-value { font-size: 12px; margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cell-sub { font-size: 10px; color: var(--text-dim); margin-top: 2px; min-height: 12px; }
</style>
