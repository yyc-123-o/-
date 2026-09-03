<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts";
import { getMasteryColor } from "@/utils/mastery";

const props = defineProps<{ values: Record<string, number> }>();
const el = ref<HTMLElement>();
let chart: echarts.ECharts | null = null;

function render() {
  if (!el.value) return;
  chart ||= echarts.init(el.value);
  const names = Object.keys(props.values);
  chart.setOption({
    animation: true,
    animationDuration: 450,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      valueFormatter: (value: number) => `${Math.round(value * 100)}%`,
    },
    grid: { left: 4, right: 16, top: 18, bottom: 8, containLabel: true },
    xAxis: { type: "value", max: 1, show: false },
    yAxis: {
      type: "category",
      data: names,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#52647e", fontSize: 11 },
    },
    series: [{
      type: "bar",
      data: names.map((name) => ({
        value: props.values[name],
        itemStyle: { color: getMasteryColor(props.values[name]), borderRadius: [0, 3, 3, 0] },
      })),
      barWidth: 11,
      showBackground: true,
      backgroundStyle: { color: "#edf2f7", borderRadius: [0, 3, 3, 0] },
      label: {
        show: true,
        position: "right",
        formatter: (item: { value: number }) => `${Math.round(item.value * 100)}%`,
        color: "#1f314a",
        fontSize: 11,
      },
      markLine: {
        silent: true,
        symbol: "none",
        data: [{ xAxis: 0.75 }],
        lineStyle: { color: "#c7d3e1", type: "dashed", width: 1 },
        label: { show: false },
      },
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
  <div ref="el" class="mastery-chart" aria-label="知识领域掌握度柱状图" />
</template>
