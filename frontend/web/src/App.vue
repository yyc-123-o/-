<script setup lang="ts">
import { computed } from "vue";
import { RouterView, useRoute } from "vue-router";
import AppShell from "@/layouts/AppShell.vue";

const route = useRoute();
const isPublic = computed(() => route.meta.layout === "public");
</script>

<template>
  <Transition name="page-shell" mode="out-in">
    <RouterView v-if="isPublic" :key="route.fullPath" />
    <AppShell v-else :key="route.fullPath" />
  </Transition>
</template>
