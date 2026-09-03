<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    src: string;
    alt?: string;
    className?: string;
    objectPosition?: string;
    mobileObjectPosition?: string;
  }>(),
  {
    alt: "",
    className: "",
    objectPosition: "center center",
    mobileObjectPosition: undefined,
  },
);

const artworkStyle = computed(() => ({
  "--story-object-position": props.objectPosition,
  "--story-object-position-mobile": props.mobileObjectPosition || props.objectPosition,
}));
</script>

<template>
  <img
    class="story-artwork"
    :class="className"
    :style="artworkStyle"
    :src="src"
    :alt="alt"
    :aria-hidden="alt ? undefined : 'true'"
    loading="eager"
    decoding="async"
  />
</template>

<style scoped>
.story-artwork {
  position: absolute;
  inset: -20% -10%;
  z-index: 0;
  width: 120%;
  height: 140%;
  max-width: none;
  object-fit: cover;
  object-position: var(--story-object-position);
  pointer-events: none;
  user-select: none;
  opacity: 0.9;
  -webkit-mask-image: linear-gradient(180deg, transparent 0%, #000 13%, #000 84%, transparent 100%);
  mask-image: linear-gradient(180deg, transparent 0%, #000 13%, #000 84%, transparent 100%);
}

@media (max-width: 780px) {
  .story-artwork {
    inset: -14% -18%;
    width: 136%;
    height: 132%;
    object-position: var(--story-object-position-mobile);
  }
}
</style>
