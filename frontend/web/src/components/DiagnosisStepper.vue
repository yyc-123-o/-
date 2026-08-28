<script setup lang="ts">
defineProps<{ current: number; completed: number[] }>();
defineEmits<{ select: [number] }>();
const steps = [
  { title: "基础信息", desc: "了解背景和目标" },
  { title: "知识水平", desc: "评估掌握情况" },
  { title: "学习画像", desc: "生成个性化建议" },
];
</script>
<template>
  <div class="stepper">
    <button v-for="(step, index) in steps" :key="step.title" class="stepper-item" :class="{ active: current === index + 1, complete: completed.includes(index + 1) }" @click="$emit('select', index + 1)">
      <span class="step-number">{{ completed.includes(index + 1) ? "✓" : `0${index + 1}` }}</span>
      <span><b>{{ step.title }}</b><small>{{ step.desc }}</small></span>
      <em>{{ completed.includes(index + 1) ? "已完成" : current === index + 1 ? "进行中" : "待开始" }}</em>
    </button>
  </div>
</template>
