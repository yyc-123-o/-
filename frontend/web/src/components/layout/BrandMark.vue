<script setup lang="ts">
import brandLogo from "@/assets/brand-logo.png";

withDefaults(
  defineProps<{
    size?: number;
  }>(),
  {
    size: 44,
  },
);
</script>

<template>
  <span class="brand-emblem" :style="{ width: `${size}px`, height: `${size}px` }" aria-hidden="true">
    <img :src="brandLogo" alt="" class="brand-emblem__img" />
  </span>
</template>

<style scoped>
.brand-emblem {
  display: inline-grid;
  place-items: center;
  flex: none;
  vertical-align: middle;
  overflow: hidden;
  background: transparent;
}

.brand-emblem__img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  object-position: center;
  background: transparent;
}
</style>
