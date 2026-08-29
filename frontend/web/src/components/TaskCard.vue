<script setup lang="ts">
import { ArrowRight, CheckCircle2, Circle } from "lucide-vue-next";
defineProps<{ title: string; description: string; status?: string; duration?: string }>();
defineEmits<{ open: [] }>();
</script>
<template>
  <article class="task-card">
    <span class="task-check"><CheckCircle2 v-if="status === 'done'" :size="18" /><Circle v-else :size="18" /></span>
    <div><strong>{{ title }}</strong><p>{{ description }}</p><small>{{ duration || "约 15 分钟" }}</small></div>
    <button class="icon-button" title="打开任务" @click="$emit('open')"><ArrowRight :size="18" /></button>
  </article>
</template>
