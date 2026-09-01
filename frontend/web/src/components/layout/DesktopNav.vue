<script setup lang="ts">
import type { HomeNavItem } from "@/composables/useHomeNavbar";

defineProps<{
  activeKey: string;
  items: HomeNavItem[];
}>();

const emit = defineEmits<{
  (event: "navigate", key: string): void;
}>();
</script>

<template>
  <nav class="desktop-nav" aria-label="产品导航">
    <button
      v-for="item in items"
      :key="item.key"
      type="button"
      class="desktop-nav__item"
      :class="{ 'is-active': activeKey === item.key }"
      @click="emit('navigate', item.key)"
    >
      <span>{{ item.label }}</span>
    </button>
  </nav>
</template>

<style scoped>
.desktop-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-width: 0;
}

.desktop-nav__item {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 42px;
  padding: 0 14px;
  color: #51647c;
  background: transparent;
  border: 0;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
  transition: color 0.18s ease, transform 0.18s ease, background-color 0.18s ease;
}

.desktop-nav__item::after {
  position: absolute;
  right: 16px;
  bottom: 7px;
  left: 16px;
  height: 2px;
  content: "";
  background: transparent;
  border-radius: 99px;
  transition: background-color 0.18s ease, transform 0.18s ease;
}

.desktop-nav__item:hover {
  color: #2f6fec;
  transform: translateY(-1px);
  background: rgba(47, 111, 236, 0.05);
}

.desktop-nav__item.is-active {
  color: #2f6fec;
}

.desktop-nav__item.is-active::after {
  background: #2f6fec;
}

@media (max-width: 1110px) {
  .desktop-nav {
    gap: 4px;
  }

  .desktop-nav__item {
    padding: 0 11px;
    font-size: 14px;
  }

  .desktop-nav__item:nth-child(4),
  .desktop-nav__item:nth-child(5) {
    display: none;
  }
}

@media (max-width: 960px) {
  .desktop-nav {
    display: none;
  }
}
</style>
