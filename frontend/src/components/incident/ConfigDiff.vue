<script setup lang="ts">
defineProps<{ diff: string[] }>();
</script>

<template>
  <pre class="diff mono"><code><span
    v-for="(line, i) in diff"
    :key="i"
    :class="{ add: line.startsWith('+'), del: line.startsWith('-') }"
  >{{ line }}
</span></code></pre>
</template>

<style scoped>
.diff {
  margin: 0; padding: 10px 14px; font-size: 11.5px; line-height: 1.55;
  background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius);
  overflow-x: auto;
}
.add { color: var(--ok); }
.del { color: var(--crit); }
</style>
