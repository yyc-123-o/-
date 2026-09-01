<script setup lang="ts">
import { computed } from "vue";
import { RouterView, useRoute } from "vue-router";
import AppShell from "@/layouts/AppShell.vue";

const route = useRoute();
const publicRoutes = new Set(["/", "/login", "/register"]);
const isPublicPage = computed(() => publicRoutes.has(route.path));
</script>

<template>
  <Transition name="page-shell" mode="out-in">
    <RouterView v-if="isPublicPage" :key="route.fullPath" />
    <AppShell v-else :key="route.path" />
  </Transition>
</template>
