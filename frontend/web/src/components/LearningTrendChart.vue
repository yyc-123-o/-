<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts";

interface TrendPoint {
  label: string;
  mastery: number | null;
  accuracy: number | null;
}

const props = defineProps<{ points: TrendPoint[] }>();
const el = ref<HTMLElement>();
let chart: echarts.ECharts | null = null;

function render() {
  if (!el.value || props.points.length < 2) return;
  chart ||= echarts.init(el.value);
  chart.setOption({
    animation: true,
    animationDuration: 500,
    tooltip: {
      trigger: "axis",
      valueFormatter: (value: number) => `${Math.round(value * 100)}%`,
    },
    grid: { left: 8, right: 12, top: 18, bottom: 8, containLabel: true },
    xAxis: {
      type: "category",
      data: props.points.map((point) => point.label),
      boundaryGap: false,
      axisLine: { lineStyle: { color: "#dfe7ef" } },
      axisTick: { show: false },
      axisLabel: { color: "#71809a", fontSize: 10 },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 1,
      interval: 0.25,
      axisLabel: {
        color: "#8a99ad",
        fontSize: 10,
        formatter: (value: number) => `${Math.round(value * 100)}%`,
      },
      splitLine: { lineStyle: { color: "#edf1f5" } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        name: "平均掌握度",
        type: "line",
        smooth: true,
        showSymbol: true,
        symbolSize: 7,
        data: props.points.map((point) => point.mastery),
        connectNulls: false,
        lineStyle: { color: "#2f6bff", width: 2 },
        itemStyle: { color: "#2f6bff", borderColor: "#fff", borderWidth: 2 },
      },
      {
        name: "测评正确率",
        type: "line",
        smooth: true,
        showSymbol: true,
        symbolSize: 7,
        data: props.points.map((point) => point.accuracy),
        connectNulls: false,
        lineStyle: { color: "#269eab", width: 2 },
        itemStyle: { color: "#269eab", borderColor: "#fff", borderWidth: 2 },
      },
    ],
  });
}

function resize() {
  chart?.resize();
}

onMounted(() => {
  nextTick(render);
  window.addEventListener("resize", resize);
});

watch(() => props.points, () => nextTick(render), { deep: true });

onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
  chart?.dispose();
});
</script>

<template>
  <div ref="el" class="learning-trend-chart" aria-label="学习表现趋势图" />
</template>
