<script setup lang="ts">
import { computed } from "vue";
const props = withDefaults(defineProps<{ value: number; label?: string; size?: number }>(), { label: "掌握度", size: 110 });
const dash = computed(() => `${Math.max(0, Math.min(props.value, 1)) * 251.2} 251.2`);
</script>
<template>
  <div class="progress-ring" :style="{ width: `${size}px`, height: `${size}px` }">
    <svg viewBox="0 0 100 100"><circle class="ring-track" cx="50" cy="50" r="40" /><circle class="ring-value" cx="50" cy="50" r="40" :style="{ strokeDasharray: dash }" /></svg>
    <div><strong>{{ Math.round(value * 100) }}%</strong><span>{{ label }}</span></div>
  </div>
</template>
