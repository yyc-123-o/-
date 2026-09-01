<script setup lang="ts">
import mascotImage from "@/assets/mascot.png";

withDefaults(
  defineProps<{
    size?: number;
    framed?: boolean;
  }>(),
  {
    size: 420,
    framed: true,
  },
);
</script>

<template>
  <div class="mascot-figure" :class="{ 'is-framed': framed }" :style="{ maxWidth: `${size}px` }">
    <img :src="mascotImage" alt="知径吉祥物" class="mascot-figure__img" />
  </div>
</template>

<style scoped>
.mascot-figure {
  display: grid;
  place-items: center;
  width: 100%;
}

.mascot-figure.is-framed {
  padding: 18px;
  background: radial-gradient(circle at 30% 20%, rgba(47, 111, 236, 0.08), transparent 40%),
    radial-gradient(circle at 70% 78%, rgba(11, 145, 172, 0.08), transparent 35%),
    rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(220, 231, 243, 0.9);
  border-radius: 28px;
  box-shadow: 0 18px 40px rgba(43, 77, 120, 0.08);
}

.mascot-figure__img {
  display: block;
  width: 100%;
  height: auto;
  object-fit: contain;
  object-position: center;
}
</style>
