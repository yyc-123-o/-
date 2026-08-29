<script setup lang="ts">
import { LockKeyhole, Play, Check } from "lucide-vue-next";
import type { PathNode } from "@/types/planning";
defineProps<{ node: PathNode }>();
defineEmits<{ select: [string] }>();
</script>
<template>
  <button class="knowledge-node" :class="`node-${node.status}`" @click="$emit('select', node.concept_id)">
    <span class="node-state"><Check v-if="node.status === 'completed'" :size="14" /><LockKeyhole v-else-if="node.status === 'blocked'" :size="14" /><Play v-else :size="14" /></span>
    <span class="node-copy"><b>{{ node.title || node.name || node.concept_id }}</b><small>{{ node.depth || "intermediate" }} · {{ node.estimated_minutes || 20 }} 分钟</small></span>
    <span v-if="typeof node.mastery_score === 'number'" class="node-score">{{ Math.round(node.mastery_score * 100) }}%</span>
  </button>
</template>
