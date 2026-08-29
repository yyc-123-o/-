<script setup lang="ts">
import KnowledgeNode from "./KnowledgeNode.vue";
import type { PathNode } from "@/types/planning";
defineProps<{ nodes: PathNode[] }>();
defineEmits<{ select: [string] }>();
</script>
<template>
  <div class="path-map">
    <div class="path-line" />
    <KnowledgeNode v-for="node in nodes" :key="node.concept_id" :node="node" @select="$emit('select', $event)" />
  </div>
</template>
