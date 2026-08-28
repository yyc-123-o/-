<script setup lang="ts">
import type { Component } from "vue";
defineProps<{ label: string; value: string; hint?: string; icon: Component; tone?: "blue" | "purple" | "green" | "amber" }>();
</script>
<template>
  <article class="stat-card">
    <span class="stat-icon" :class="`tone-${tone || 'blue'}`"><component :is="icon" :size="19" /></span>
    <div><span>{{ label }}</span><strong>{{ value }}</strong><small v-if="hint">{{ hint }}</small></div>
  </article>
</template>
