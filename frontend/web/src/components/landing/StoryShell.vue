<script setup lang="ts">
import GlobalAtmosphere from "./GlobalAtmosphere.vue";

const storyPath = "/assets/landing/story-path.svg";
</script>

<template>
  <div class="story-shell">
    <GlobalAtmosphere />
    <img class="story-shell__path" :src="storyPath" alt="" aria-hidden="true" />
    <div class="story-shell__content">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.story-shell {
  position: relative;
  min-height: 100vh;
  overflow: clip;
  background: #f4f8fd;
}

.story-shell__content {
  position: relative;
  z-index: 1;
}

.story-shell__path {
  position: absolute;
  inset: 0;
  z-index: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  pointer-events: none;
  user-select: none;
  opacity: 0.22;
  mix-blend-mode: soft-light;
}
</style>
