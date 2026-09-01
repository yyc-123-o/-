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
  <RouterLink :to="to" class="brand-wordmark" :class="{ 'is-compact': compact }" aria-label="织知成径首页">
    <BrandMark :size="compact ? 34 : 44" class="brand-wordmark__mark" /> <!-- 修改点 -->
    <span class="brand-wordmark__copy">
      <strong>织知成径</strong>
    </span>
  </RouterLink>
</template>

<style scoped>
.brand-wordmark {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  width: fit-content;
  height: fit-content;
  min-width: 0;
  color: #1d3250;
  text-decoration: none;
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.brand-wordmark:hover {
  transform: translateY(-1px);
}

.brand-wordmark__mark {
  display: block;
  flex: none;
}

.brand-wordmark__copy {
  min-width: 0;
}

.brand-wordmark__copy strong {
  display: block;
  color: #1d3250;
  font-size: 18px;
  font-weight: 800;
  line-height: 1;
}

.is-compact .brand-wordmark__mark {
  width: 34px; /* 修改点 */
  height: 34px; /* 修改点 */
}

.is-compact .brand-wordmark__copy strong {
  font-size: 16px; /* 修改点 */
}

@media (max-width: 720px) {
  .brand-wordmark {
    gap: 8px;
  }

  .brand-wordmark__copy strong {
    font-size: 17px;
  }
}
</style>
