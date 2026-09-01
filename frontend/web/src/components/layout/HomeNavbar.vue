<script setup lang="ts">
import DesktopNav from "./DesktopNav.vue";
import BrandWordmark from "./BrandWordmark.vue";
import MobileMenu from "./MobileMenu.vue";
import NavbarActions from "./NavbarActions.vue";
import { homeNavItems, useHomeNavbar } from "@/composables/useHomeNavbar";

const {
  activeKey,
  closeMobileMenu,
  isMobileMenuOpen,
  isScrolled,
  scrollToSection,
  toggleMobileMenu,
} = useHomeNavbar();
</script>

<template>
  <header class="home-navbar" :class="{ 'is-scrolled': isScrolled }">
    <div class="home-navbar__inner">
      <BrandWordmark />

      <DesktopNav :active-key="activeKey" :items="homeNavItems" @navigate="scrollToSection" />

      <NavbarActions :mobile-menu-open="isMobileMenuOpen" @toggle-menu="toggleMobileMenu" />
    </div>
  </header>

  <MobileMenu
    :active-key="activeKey"
    :items="homeNavItems"
    :open="isMobileMenuOpen"
    @close="closeMobileMenu"
    @navigate="scrollToSection"
  />
</template>

<style scoped>
.home-navbar {
  position: sticky;
  top: 0;
  z-index: 60;
  padding: 12px 20px 0;
  background: rgba(255, 255, 255, 0.92);
  border-bottom: 1px solid rgba(223, 232, 243, 0.72);
  backdrop-filter: blur(10px);
  transition: background-color 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease, transform 0.22s ease;
}

.home-navbar.is-scrolled {
  background: rgba(255, 255, 255, 0.82);
  border-bottom-color: rgba(212, 223, 236, 0.94);
  box-shadow: 0 10px 28px rgba(43, 77, 120, 0.06);
}

.home-navbar__inner {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 22px;
  max-width: 1360px;
  min-height: 76px;
  margin: 0 auto;
  padding: 0 8px 12px;
}

@media (max-width: 1110px) {
  .home-navbar__inner {
    gap: 16px;
    padding-left: 0;
    padding-right: 0;
  }
}

@media (max-width: 960px) {
  .home-navbar {
    padding-left: 14px;
    padding-right: 14px;
  }

  .home-navbar__inner {
    grid-template-columns: auto 1fr auto;
    min-height: 72px;
  }
}

@media (max-width: 720px) {
  .home-navbar {
    padding-top: 10px;
  }

  .home-navbar__inner {
    min-height: 68px;
    padding-bottom: 10px;
  }
}
</style>
