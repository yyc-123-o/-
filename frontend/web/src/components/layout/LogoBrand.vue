<script setup lang="ts">
import { RouterLink, type RouteLocationRaw } from "vue-router";
import BrandMark from "./BrandMark.vue";

withDefaults(
  defineProps<{
    compact?: boolean;
    to?: RouteLocationRaw;
  }>(),
  {
    compact: false,
    to: "/",
  },
);
</script>

<template>
  <RouterLink :to="to" class="logo-brand" :class="{ 'is-compact': compact }" aria-label="织知成径首页">
    <BrandMark :size="compact ? 40 : 44" class="logo-brand__mark" />
    <span class="logo-brand__copy">
      <strong>织知成径</strong>
      <small>AI 课程智能平台</small>
    </span>
  </RouterLink>
</template>

<style scoped>
.logo-brand { display: inline-flex; align-items: center; gap: 12px; min-width: 0; color: #1d3250; transition: transform .2s ease, opacity .2s ease; }
.logo-brand:hover { transform: translateY(-1px); }
.logo-brand__mark { flex: none; }
.logo-brand__copy { min-width: 0; display: grid; gap: 2px; }
.logo-brand__copy strong, .logo-brand__copy small { display: block; line-height: 1.1; }
.logo-brand__copy strong { font-size: 18px; font-weight: 800; color: #1d3250; }
.logo-brand__copy small { margin-top: 3px; color: #6d7f96; font-size: 11px; font-weight: 500; }
.is-compact .logo-brand__copy strong { font-size: 17px; }
.is-compact .logo-brand__copy small { font-size: 10px; }
@media (max-width: 720px) { .logo-brand__copy strong { font-size: 17px; } .logo-brand__copy small { font-size: 10px; } }
</style>
