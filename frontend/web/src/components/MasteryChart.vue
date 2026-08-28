<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts";
const props = defineProps<{ values: Record<string, number> }>();
const el = ref<HTMLElement>();
let chart: echarts.ECharts | null = null;
function render() {
  if (!el.value) return;
  chart ||= echarts.init(el.value);
  const names = Object.keys(props.values);
  chart.setOption({
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: 4, right: 8, top: 12, bottom: 8, containLabel: true },
    xAxis: { type: "value", max: 1, show: false },
    yAxis: { type: "category", data: names, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "#64748b", fontSize: 11 } },
    series: [{ type: "bar", data: names.map((name) => ({ value: props.values[name], itemStyle: { color: props.values[name] >= 0.6 ? "#20a866" : props.values[name] >= 0.4 ? "#d99527" : "#e05b63", borderRadius: 8 } })), barWidth: 10, showBackground: true, backgroundStyle: { color: "#edf2f7", borderRadius: 8 }, label: { show: true, position: "right", formatter: (item: { value: number }) => `${Math.round(item.value * 100)}%`, color: "#1f314a", fontSize: 11 } }],
  });
}
onMounted(() => nextTick(render));
watch(() => props.values, () => nextTick(render), { deep: true });
onBeforeUnmount(() => chart?.dispose());
</script>
<template><div ref="el" class="mastery-chart" /></template>
