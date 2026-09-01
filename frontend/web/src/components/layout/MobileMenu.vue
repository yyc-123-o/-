<script setup lang="ts">
import { X } from "lucide-vue-next";
import { RouterLink } from "vue-router";
import BrandWordmark from "./BrandWordmark.vue";
import type { HomeNavItem } from "@/composables/useHomeNavbar";

defineProps<{ activeKey: string; items: HomeNavItem[]; open: boolean }>();
const emit = defineEmits<{ (event: "close"): void; (event: "navigate", key: string): void }>();
</script>

<template>
  <Transition name="home-menu">
    <div v-if="open" class="mobile-menu" @click.self="emit('close')">
      <div class="mobile-menu__panel" role="dialog" aria-modal="true" aria-label="产品导航菜单">
        <div class="mobile-menu__head">
          <BrandWordmark compact />
          <button type="button" class="mobile-menu__close" aria-label="关闭导航菜单" @click="emit('close')">
            <X :size="18" />
          </button>
        </div>
        <nav class="mobile-menu__nav" aria-label="移动端产品导航">
          <button
            v-for="item in items"
            :key="item.key"
            type="button"
            class="mobile-menu__item"
            :class="{ 'is-active': activeKey === item.key }"
            @click="emit('navigate', item.key)"
          >
            <span>{{ item.label }}</span>
          </button>
        </nav>
        <div class="mobile-menu__actions">
          <RouterLink to="/login" class="mobile-menu__ghost" @click="emit('close')">登录</RouterLink>
          <RouterLink to="/register" class="mobile-menu__cta" @click="emit('close')">开始使用</RouterLink>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.mobile-menu {
  position: fixed;
  inset: 0;
  z-index: 80;
  background: rgba(16, 28, 46, 0.22);
  backdrop-filter: blur(4px);
}

.mobile-menu__panel {
  position: absolute;
  top: 12px;
  right: 12px;
  bottom: 12px;
  width: min(86vw, 340px);
  padding: 16px;
  background: rgba(255, 255, 255, 0.98);
  border: 1px solid rgba(216, 226, 238, 0.9);
  border-radius: 22px;
  box-shadow: 0 24px 56px rgba(23, 42, 67, 0.18);
}

.mobile-menu__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
}

.mobile-menu__close {
  display: inline-grid;
  place-items: center;
  width: 38px;
  height: 38px;
  color: #5b6f87;
  background: #f5f8fc;
  border: 1px solid #e2ebf5;
  border-radius: 12px;
}

.mobile-menu__nav {
  display: grid;
  gap: 8px;
}

.mobile-menu__item {
  display: flex;
  align-items: center;
  min-height: 48px;
  padding: 0 14px;
  color: #354a65;
  background: #f7f9fd;
  border: 1px solid transparent;
  border-radius: 14px;
  font-size: 15px;
  font-weight: 600;
  text-align: left;
  transition: transform 0.18s ease, color 0.18s ease, background-color 0.18s ease, border-color 0.18s ease;
}

.mobile-menu__item:hover,
.mobile-menu__item.is-active {
  color: #2f6fec;
  background: #edf4ff;
  border-color: #cfe0ff;
}

.mobile-menu__actions {
  display: grid;
  gap: 10px;
  margin-top: 18px;
}

.mobile-menu__ghost,
.mobile-menu__cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 700;
}

.mobile-menu__ghost {
  color: #51647c;
  background: #f5f8fc;
  border: 1px solid #e2ebf5;
}

.mobile-menu__cta {
  color: #fff;
  background: #356ae6;
  box-shadow: 0 10px 24px rgba(47, 111, 236, 0.16);
}

.home-menu-enter-active,
.home-menu-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.home-menu-enter-from,
.home-menu-leave-to {
  opacity: 0;
}

.home-menu-enter-from .mobile-menu__panel,
.home-menu-leave-to .mobile-menu__panel {
  transform: translateX(16px);
}

@media (min-width: 961px) {
  .mobile-menu {
    display: none;
  }
}
</style>
