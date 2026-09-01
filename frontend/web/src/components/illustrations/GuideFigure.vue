<script setup lang="ts">
withDefaults(
  defineProps<{
    size?: number;
  }>(),
  {
    size: 180,
  },
);
</script>

<template>
  <div class="guide-figure" :style="{ width: `${size}px` }" aria-hidden="true">
    <svg viewBox="0 0 220 220" role="presentation" class="guide-figure__svg">
      <defs>
        <linearGradient id="guide-grad" x1="18%" y1="18%" x2="82%" y2="82%">
          <stop offset="0%" stop-color="#2f6fec" />
          <stop offset="100%" stop-color="#18a7a0" />
        </linearGradient>
        <linearGradient id="guide-soft" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#eef4ff" />
          <stop offset="100%" stop-color="#f7fbff" />
        </linearGradient>
      </defs>

      <circle cx="110" cy="110" r="92" fill="url(#guide-soft)" />
      <circle cx="110" cy="110" r="75" fill="none" stroke="rgba(53, 106, 230, 0.16)" stroke-width="2" stroke-dasharray="8 10" class="guide-figure__orbit" />
      <path d="M60 128C80 102 94 92 110 92C127 92 142 106 160 82" fill="none" stroke="url(#guide-grad)" stroke-width="4" stroke-linecap="round" class="guide-figure__path" />

      <g class="guide-figure__node">
        <circle cx="60" cy="128" r="10" fill="#fff" stroke="#2f6fec" stroke-width="4" />
        <circle cx="110" cy="92" r="13" fill="#2f6fec" />
        <circle cx="160" cy="82" r="10" fill="#fff" stroke="#18a7a0" stroke-width="4" />
      </g>

      <rect x="86" y="102" width="48" height="48" rx="16" fill="#fff" stroke="#cfe0ff" stroke-width="2" class="guide-figure__core" />
      <path d="M98 120h24M98 130h14" stroke="#2f6fec" stroke-width="4" stroke-linecap="round" />
      <circle cx="110" cy="126" r="18" fill="none" stroke="rgba(24, 167, 160, 0.32)" stroke-width="2" />

      <g class="guide-figure__sparkles">
        <circle cx="52" cy="72" r="4" fill="#5bb7ff" />
        <circle cx="170" cy="54" r="4" fill="#6dd3cc" />
        <circle cx="176" cy="156" r="4" fill="#8c7dff" />
        <circle cx="48" cy="160" r="4" fill="#ffc96a" />
      </g>
    </svg>
  </div>
</template>

<style scoped>
.guide-figure {
  display: grid;
  place-items: center;
  aspect-ratio: 1;
}

.guide-figure__svg {
  display: block;
  width: 100%;
  height: auto;
}

.guide-figure__orbit {
  transform-origin: center;
  animation: orbit-rotate 18s linear infinite;
}

.guide-figure__path,
.guide-figure__core {
  animation: guide-breathe 3.4s ease-in-out infinite;
}

.guide-figure__node {
  animation: guide-float 4.8s ease-in-out infinite;
}

.guide-figure__sparkles {
  animation: sparkle-drift 5.6s ease-in-out infinite;
}

@keyframes orbit-rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes guide-breathe {
  0%, 100% { opacity: 0.95; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.015); }
}

@keyframes guide-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-4px); }
}

@keyframes sparkle-drift {
  0%, 100% { transform: translateY(0); opacity: 0.9; }
  50% { transform: translateY(3px); opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .guide-figure__orbit,
  .guide-figure__path,
  .guide-figure__core,
  .guide-figure__node,
  .guide-figure__sparkles {
    animation: none !important;
  }
}
</style>
