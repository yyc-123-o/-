<script setup lang="ts">
import { ref } from "vue";
import { RouterLink } from "vue-router";
import { ArrowRight, Sparkles, X } from "lucide-vue-next";
import HomeNavbar from "@/components/layout/HomeNavbar.vue";
import HomeHeroCarousel from "@/components/landing/HomeHeroCarousel.vue";

const agentOpen = ref(false);

const agentLinks = [
  { label: "学习路径", to: "/learning-path", detail: "继续下一步规划" },
  { label: "学习记录", to: "/history", detail: "查看最近进度" },
  { label: "学情中心", to: "/diagnosis", detail: "完成能力诊断" },
];
</script>

<template>
  <div class="product-home">
    <HomeNavbar />

    <main class="home-page">
      <HomeHeroCarousel />
    </main>

    <button class="home-agent-entry" type="button" aria-label="打开织知助手" :aria-expanded="agentOpen" @click="agentOpen = !agentOpen">
      <Sparkles :size="16" />
      <span>织知助手</span>
    </button>

    <div v-if="agentOpen" class="home-agent-backdrop" @click="agentOpen = false" />
    <aside v-if="agentOpen" class="home-agent-panel" aria-label="织知助手面板">
      <div class="home-agent-panel__head">
        <div>
          <p class="eyebrow">织知助手</p>
          <h3>下一步可以做什么</h3>
        </div>
        <button class="home-agent-panel__close" type="button" aria-label="关闭织知助手" @click="agentOpen = false">
          <X :size="16" />
        </button>
      </div>

      <p class="home-agent-panel__copy">你可以继续查看学习路径、学习记录，或者直接进入学情诊断，接着完成当前任务。</p>

      <div class="home-agent-panel__links">
        <RouterLink
          v-for="item in agentLinks"
          :key="item.to"
          :to="item.to"
          class="home-agent-panel__link"
          @click="agentOpen = false"
        >
          <span>
            <b>{{ item.label }}</b>
            <small>{{ item.detail }}</small>
          </span>
          <ArrowRight :size="16" />
        </RouterLink>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.product-home {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100dvh;
  overflow: hidden;
  background: linear-gradient(180deg, #f4f8fe 0%, #f8fbff 46%, #edf5fb 100%);
}

.home-page {
  position: relative;
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.home-agent-entry {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 92;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 52px;
  padding: 0 16px;
  color: #fff;
  background: #2f6fed;
  border: 0;
  border-radius: 999px;
  box-shadow: 0 12px 28px rgba(47, 111, 236, 0.18);
  font-size: 15px;
  font-weight: 800;
}

.home-agent-entry:hover {
  background: #245fd3;
}

.home-agent-backdrop {
  position: fixed;
  inset: 0;
  z-index: 90;
  background: rgba(16, 39, 70, 0.08);
}

.home-agent-panel {
  position: fixed;
  right: 24px;
  bottom: 88px;
  z-index: 91;
  display: grid;
  gap: 14px;
  width: min(332px, calc(100vw - 32px));
  padding: 16px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(223, 232, 243, 0.95);
  border-radius: 18px;
  box-shadow: 0 18px 44px rgba(40, 75, 120, 0.14);
}

.home-agent-panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.home-agent-panel__head h3 {
  margin: 5px 0 0;
  color: #102746;
  font-size: 18px;
  line-height: 1.3;
}

.home-agent-panel__copy {
  margin: 0;
  color: #62748d;
  font-size: 14px;
  line-height: 1.7;
}

.home-agent-panel__links {
  display: grid;
  gap: 10px;
}

.home-agent-panel__link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 13px;
  color: #173151;
  background: #f8fbff;
  border: 1px solid #dce5f0;
  border-radius: 14px;
}

.home-agent-panel__link b,
.home-agent-panel__link small {
  display: block;
}

.home-agent-panel__link b {
  font-size: 14px;
}

.home-agent-panel__link small {
  margin-top: 2px;
  color: #64748d;
  font-size: 12px;
}

.home-agent-panel__link:hover {
  color: #245fd3;
  background: #edf4ff;
  border-color: #c7d8f5;
}

.home-agent-panel__close {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  color: #64748d;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 9px;
}

.home-agent-panel__close:hover {
  color: #102746;
  background: #f4f8fd;
  border-color: #dce5f0;
}

@media (max-width: 760px) {
  .home-agent-entry {
    right: 16px;
    bottom: 16px;
    height: 48px;
    padding: 0 14px;
  }

  .home-agent-panel {
    right: 16px;
    bottom: 76px;
    width: min(320px, calc(100vw - 24px));
  }
}
</style>
