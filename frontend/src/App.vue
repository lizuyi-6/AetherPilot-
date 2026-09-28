<script setup lang="ts">
import { onMounted } from "vue";
import { RouterView, RouterLink } from "vue-router";
import { useSystemStore } from "./stores/system";
import { i18n, t } from "./i18n";

const system = useSystemStore();
onMounted(() => {
  system.refresh();
  system.connectWs();
});
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <RouterLink to="/" class="logo mono">AETHERPILOT</RouterLink>
        <span class="tagline">{{ t("tagline") }}</span>
      </div>
      <nav class="nav mono">
        <RouterLink to="/">{{ t("home") }}</RouterLink>
        <RouterLink to="/skills">{{ t("skills") }}</RouterLink>
        <button class="lang" @click="i18n.toggle()">{{ i18n.lang === "en" ? "中文" : "EN" }}</button>
      </nav>
    </header>
    <main>
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.shell { display: flex; flex-direction: column; height: 100vh; }
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 22px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  flex: 0 0 auto;
}
.brand { display: flex; align-items: baseline; gap: 14px; }
.logo { font-size: 16px; letter-spacing: 0.28em; color: var(--text); font-weight: 600; }
.tagline { color: var(--text-dim); font-size: 11px; letter-spacing: 0.1em; }
.nav { display: flex; gap: 18px; align-items: center; font-size: 11px; letter-spacing: 0.14em; }
.nav a { color: var(--text-dim); }
.nav a.router-link-active { color: var(--accent); }
.lang { padding: 3px 10px; font-size: 10px; }
main { flex: 1; overflow: auto; }
</style>
