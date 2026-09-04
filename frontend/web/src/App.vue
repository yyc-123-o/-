<script setup lang="ts">
import { computed } from "vue";
import { RouterView, useRoute } from "vue-router";
import AppShell from "@/layouts/AppShell.vue";

const route = useRoute();
const publicRoutes = new Set(["/", "/login", "/register"]);
const isPublicPage = computed(() => publicRoutes.has(route.path));
</script>

<template>
  <RouterView v-slot="{ Component }">
    <Transition name="page-shell" mode="out-in">
      <component v-if="isPublicPage" :is="Component" :key="route.fullPath" />
      <AppShell v-else key="app-shell">
        <!-- Private pages must survive query/hash updates. Learning-path updates
             its query state while generating; remounting here would restart it. -->
        <component :is="Component" :key="route.name || route.path" />
      </AppShell>
    </Transition>
  </RouterView>
</template>
