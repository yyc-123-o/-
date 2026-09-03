<script setup lang="ts">
const ambientStars = "/assets/landing/ambient-stars.svg";
</script>

<template>
  <div class="global-atmosphere" aria-hidden="true">
    <img class="global-atmosphere__stars" :src="ambientStars" alt="" />
  </div>
</template>

<style scoped>
.global-atmosphere {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
  background:
    radial-gradient(ellipse at 17% 7%, rgba(104, 170, 238, 0.18), transparent 29%),
    radial-gradient(ellipse at 80% 21%, rgba(78, 191, 180, 0.12), transparent 27%),
    radial-gradient(ellipse at 55% 67%, rgba(105, 170, 230, 0.1), transparent 31%),
    linear-gradient(180deg, #f6faff 0%, #f2f8fd 34%, #f7fbfd 68%, #eff7fa 100%);
}

.global-atmosphere::before {
  position: absolute;
  inset: 0;
  content: "";
  opacity: 0.24;
  background-image:
    radial-gradient(circle, rgba(53, 106, 230, 0.34) 0 1px, transparent 1.4px),
    radial-gradient(circle, rgba(24, 167, 160, 0.22) 0 1px, transparent 1.5px);
  background-position: 0 0, 26px 34px;
  background-size: 58px 58px, 82px 82px;
  mask-image: linear-gradient(180deg, #000 0%, rgba(0, 0, 0, 0.5) 42%, transparent 92%);
}

.global-atmosphere::after {
  position: absolute;
  inset: 0;
  content: "";
  opacity: 0.42;
  background:
    linear-gradient(180deg, transparent 0 48%, rgba(255, 255, 255, 0.35) 66%, transparent 88%),
    radial-gradient(ellipse at 50% 100%, rgba(24, 167, 160, 0.08), transparent 45%);
}

.global-atmosphere__stars {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0.38;
  object-fit: cover;
  object-position: center top;
}

@media (max-width: 780px) {
  .global-atmosphere::before {
    opacity: 0.18;
    background-size: 48px 48px, 72px 72px;
  }

  .global-atmosphere__stars {
    opacity: 0.25;
  }
}
</style>
