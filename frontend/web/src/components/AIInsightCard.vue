<script setup lang="ts">
import { Sparkles } from "lucide-vue-next";
defineProps<{ title?: string; body: string; suggestion?: string; action?: string }>();
defineEmits<{ action: [] }>();
</script>
<template>
  <section class="ai-insight-card">
    <div class="card-topline"><span class="ai-mark"><Sparkles :size="14" /></span><span class="eyebrow">AI INSIGHT</span></div>
    <h3>{{ title || "AI 学习顾问" }}</h3>
    <p>{{ body }}</p>
    <div v-if="suggestion" class="ai-suggestion"><Sparkles :size="15" /><span>{{ suggestion }}</span></div>
    <button v-if="action" class="button button-primary button-full" @click="$emit('action')">{{ action }} <span>→</span></button>
  </section>
</template>
