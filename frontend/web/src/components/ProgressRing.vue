<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{ value: number | null; label?: string; size?: number }>(),
  { label: "掌握度", size: 110 },
);

const normalized = computed(() =>
  typeof props.value === "number" ? Math.max(0, Math.min(props.value, 1)) : 0,
);
const dash = computed(() => `${normalized.value * 251.2} 251.2`);
</script>

<template>
  <div class="progress-ring" :style="{ width: `${size}px`, height: `${size}px` }">
    <svg viewBox="0 0 100 100" aria-hidden="true">
      <circle class="ring-track" cx="50" cy="50" r="40" />
      <circle class="ring-value" cx="50" cy="50" r="40" :style="{ strokeDasharray: dash }" />
    </svg>
    <div>
      <strong>{{ typeof value === "number" ? `${Math.round(normalized * 100)}%` : "待评估" }}</strong>
      <span>{{ label }}</span>
    </div>
  </div>
</template>
