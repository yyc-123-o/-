<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts";

const props = defineProps<{ values: Record<string, number | null>; peerValues?: Record<string, number | null> }>();
const el = ref<HTMLElement>();
let chart: echarts.ECharts | null = null;

const labels: Record<string, string> = {
  concept_understanding: "概念理解",
  theoretical_understanding: "概念理解",
  mathematical_foundation: "数学基础",
  problem_solving: "问题解决",
  practical_application: "实践应用",
  coding_ability: "实践应用",
  knowledge_transfer: "知识迁移",
  learning_stability: "学习稳定性",
  self_learning: "学习稳定性",
};

const entries = computed(() =>
  Object.entries(props.values),
);

function render() {
  if (!el.value || entries.value.length !== 6) return;
  chart ||= echarts.init(el.value);
  chart.setOption({
    animation: true,
    animationDuration: 500,
    tooltip: {
      trigger: "item",
      formatter: (params: { value: Array<number | null> }) =>
        entries.value
          .map(([key], index) => `${labels[key] || key}: ${typeof params.value[index] === "number" ? `${Math.round(params.value[index] * 100)}%` : "待评估"}`)
          .join("<br />"),
    },
    radar: {
      center: ["50%", "50%"],
      radius: "66%",
      splitNumber: 4,
      indicator: entries.value.map(([key]) => ({ name: labels[key] || key, max: 1 })),
      axisName: { color: "#52647e", fontSize: 11 },
      axisLine: { lineStyle: { color: "#dce5ef" } },
      splitLine: { lineStyle: { color: ["#eef2f6", "#e6edf4", "#dfe8f1", "#d6e1eb"] } },
      splitArea: { areaStyle: { color: ["rgba(248,250,252,.8)", "rgba(255,255,255,.3)"] } },
    },
    series: [{
      type: "radar",
      symbol: "circle",
      symbolSize: 6,
      data: [{
        value: entries.value.map(([, value]) => value),
        lineStyle: { color: "#2f6bff", width: 2 },
        itemStyle: { color: "#2f6bff" },
        areaStyle: { color: "rgba(47,107,255,.12)" },
      }],
    }],
  });
}

function resize() {
  chart?.resize();
}

onMounted(() => {
  nextTick(render);
  window.addEventListener("resize", resize);
});

watch(() => props.values, () => nextTick(render), { deep: true });

onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
  chart?.dispose();
});
</script>

<template>
  <div ref="el" class="ability-radar-chart" aria-label="综合能力雷达图" />
</template>
