<script setup lang="ts">
import { ArrowUpRight, BookOpen, Dumbbell, Lightbulb } from "lucide-vue-next";
defineProps<{ title: string; description: string; kind: string; status?: string }>();
defineEmits<{ open: [] }>();
</script>
<template>
  <article class="resource-card">
    <span class="resource-icon"><BookOpen v-if="kind === '讲解'" :size="19" /><Dumbbell v-else-if="kind === '练习'" :size="19" /><Lightbulb v-else :size="19" /></span>
    <div><span class="eyebrow">{{ kind }}</span><strong>{{ title }}</strong><p>{{ description }}</p><span class="status-pill" :class="{ 'status-pill-success': status === '正式资源' }">{{ status || "candidate preview" }}</span></div>
    <button class="icon-button" title="打开资源" @click="$emit('open')"><ArrowUpRight :size="17" /></button>
  </article>
</template>
