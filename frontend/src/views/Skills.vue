<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "../api/client";
import type { SkillSummary } from "../types";

const skills = ref<SkillSummary[]>([]);
onMounted(async () => {
  skills.value = await api.skills();
});

const PERM_CLASS: Record<string, string> = {
  allow: "ok",
  "allow-read": "ok",
  ask: "warn",
  deny: "crit",
};
</script>

<template>
  <div class="skills">
    <div v-for="skill in skills" :key="skill.name" class="skill panel">
      <div class="skill-head">
        <div>
          <h2>{{ skill.display_name }}</h2>
          <div class="skill-id mono">{{ skill.name }}@{{ skill.version }}</div>
        </div>
        <span class="tag ok">Installed</span>
      </div>
      <p class="desc">{{ skill.description }}</p>

      <div class="cols">
        <div class="col">
          <div class="col-title mono">CAPABILITIES</div>
          <div v-for="cap in skill.capabilities" :key="cap.id" class="cap">
            <div class="cap-id mono">{{ cap.id }}</div>
            <div class="cap-summary">{{ cap.summary }}</div>
          </div>
        </div>
        <div class="col">
          <div class="col-title mono">PERMISSIONS</div>
          <div v-for="(level, key) in skill.permissions" :key="key" class="perm mono">
            <span>{{ key }}</span>
            <span class="tag" :class="PERM_CLASS[level] ?? ''">{{ level.toUpperCase() }}</span>
          </div>
          <div class="col-title mono" style="margin-top: 18px">DETECTORS</div>
          <div v-for="d in skill.detectors" :key="d.id" class="det">
            <span class="det-id mono">{{ d.id }}</span>
            <span class="tag" :class="d.severity === 'critical' ? 'crit' : d.severity === 'high' ? 'warn' : ''">{{ d.severity }}</span>
          </div>
          <div class="col-title mono" style="margin-top: 18px">RECOVERY STRATEGIES</div>
          <div v-for="r in skill.recovery_strategies" :key="r.id" class="rec">
            <span class="mono">{{ r.id }}</span>
            <span class="rec-patch">{{ r.patch }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.skills { max-width: 1100px; margin: 0 auto; padding: 24px; display: flex; flex-direction: column; gap: 18px; }
.skill-head { display: flex; justify-content: space-between; align-items: flex-start; padding: 18px 22px 0; }
h2 { margin: 0; font-size: 19px; font-weight: 500; }
.skill-id { color: var(--text-faint); font-size: 11px; margin-top: 4px; }
.desc { color: var(--text-dim); padding: 8px 22px 0; margin: 0; font-size: 13px; line-height: 1.6; max-width: 70ch; }
.cols { display: grid; grid-template-columns: 1.3fr 1fr; gap: 20px; padding: 18px 22px 22px; }
.col-title { font-size: 10px; letter-spacing: 0.16em; color: var(--text-faint); margin-bottom: 10px; }
.cap { padding: 7px 0; border-bottom: 1px solid var(--border); }
.cap:last-child { border-bottom: none; }
.cap-id { font-size: 12px; color: var(--accent); }
.cap-summary { font-size: 12px; color: var(--text-dim); margin-top: 2px; }
.perm, .det { display: flex; justify-content: space-between; align-items: center; padding: 5px 0; font-size: 12px; color: var(--text-dim); }
.det-id { color: var(--text-dim); }
.rec { display: flex; flex-direction: column; padding: 5px 0; font-size: 12px; }
.rec-patch { color: var(--text-faint); font-size: 11px; margin-top: 2px; }
</style>
