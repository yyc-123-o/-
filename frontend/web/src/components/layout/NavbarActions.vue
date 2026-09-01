<script setup lang="ts">
import { ArrowRight, Menu, X } from "lucide-vue-next";
import { RouterLink } from "vue-router";

defineProps<{ mobileMenuOpen: boolean }>();
const emit = defineEmits<{ (event: "toggle-menu"): void }>();
</script>

<template>
  <div class="navbar-actions">
    <RouterLink to="/login" class="navbar-actions__ghost">登录</RouterLink>
    <RouterLink to="/register" class="navbar-actions__cta">
      <span>开始使用</span>
      <ArrowRight :size="16" />
    </RouterLink>
    <button
      type="button"
      class="navbar-actions__menu"
      :aria-expanded="mobileMenuOpen"
      aria-label="打开导航菜单"
      @click="emit('toggle-menu')"
    >
      <component :is="mobileMenuOpen ? X : Menu" :size="20" />
    </button>
  </div>
</template>

<style scoped>
.navbar-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  min-width: 0;
}

.navbar-actions__ghost,
.navbar-actions__cta,
.navbar-actions__menu {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 44px;
  border-radius: 12px;
  transition: transform 0.18s ease, background-color 0.18s ease, box-shadow 0.18s ease, color 0.18s ease;
}

.navbar-actions__ghost {
  padding: 0 18px;
  color: #51647c;
  background: transparent;
  border: 1px solid transparent;
  font-size: 15px;
  font-weight: 600;
}

.navbar-actions__ghost:hover {
  color: #2f6fec;
  background: rgba(47, 111, 236, 0.06);
}

.navbar-actions__cta {
  gap: 8px;
  padding: 0 18px;
  color: #fff;
  background: #356ae6;
  border: 1px solid #356ae6;
  box-shadow: 0 8px 18px rgba(47, 111, 236, 0.15);
  font-size: 15px;
  font-weight: 700;
}

.navbar-actions__cta:hover {
  transform: translateY(-1px);
  background: #285acb;
  box-shadow: 0 12px 24px rgba(47, 111, 236, 0.2);
}

.navbar-actions__menu {
  display: none;
  width: 44px;
  padding: 0;
  color: #2a4163;
  background: #fff;
  border: 1px solid #d8e2ee;
}

.navbar-actions__menu:hover {
  color: #2f6fec;
  background: #f3f7ff;
}

@media (max-width: 960px) {
  .navbar-actions__ghost {
    display: none;
  }

  .navbar-actions__menu {
    display: inline-flex;
  }
}

@media (max-width: 720px) {
  .navbar-actions__cta {
    min-height: 42px;
    padding: 0 14px;
  }
}
</style>
