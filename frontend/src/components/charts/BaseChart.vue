<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from "vue";
import * as echarts from "echarts";

const props = defineProps<{ option: echarts.EChartsOption; height?: string }>();
const el = ref<HTMLDivElement | null>(null);
let chart: echarts.ECharts | null = null;

onMounted(() => {
  if (!el.value) return;
  chart = echarts.init(el.value, undefined, { renderer: "canvas" });
  chart.setOption(props.option);
  window.addEventListener("resize", resize);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
  chart?.dispose();
});

function resize() {
  chart?.resize();
}

watch(
  // The option is a fresh object from a computed on every dependency change,
  // so a reference watch is sufficient — deep comparison would be wasted work.
  () => props.option,
  (option) => chart?.setOption(option, { notMerge: false })
);
</script>

<template>
  <div ref="el" :style="{ width: '100%', height: height ?? '160px' }" />
</template>
