<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import { ArrowLeft, ArrowRight, Pause, Play, Sparkles } from "lucide-vue-next";

interface BannerSlide {
  navKey: string;
  eyebrow: string;
  titleLines: string[];
  subtitle: string;
  primaryText: string;
  primaryTo: string;
  secondaryText: string;
  secondaryNavKey: string;
  tone: "blue" | "cyan" | "green" | "gold" | "navy";
  image: string;
  imagePosition: string;
  alt: string;
  infoTitle: string;
  infoBody: string;
  infoFoot: string;
}

const AUTO_PLAY_DELAY = 5000;

const slides: BannerSlide[] = [
  {
    navKey: "capability",
    eyebrow: "织知成径 · AI 辅助学习平台",
    titleLines: ["把课程知识，", "组织成每个人", "走得通的学习路径。"],
    subtitle: "连接课程资料、知识关系、学习记录与测评反馈，让每一次学习都成为下一步规划的依据。",
    primaryText: "开始学习",
    primaryTo: "/register",
    secondaryText: "了解平台如何工作",
    secondaryNavKey: "planning",
    tone: "blue",
    image: "/assets/landing/homepage-carousel/01-student-collaboration-unsplash.webp",
    imagePosition: "58% center",
    alt: "学生围坐协作学习的场景",
    infoTitle: "下一步学习",
    infoBody: "知识关系与路径正在生成",
    infoFoot: "72% 掌握度 · 实时更新",
  },
  {
    navKey: "planning",
    eyebrow: "课程知识库治理",
    titleLines: ["把分散课程资料，", "整理成可追溯的", "知识资产"],
    subtitle: "教材、课件、讲义与练习不再散落，平台会保留来源、审核状态和知识归属。",
    primaryText: "进入课程中心",
    primaryTo: "/resources",
    secondaryText: "查看知识库治理",
    secondaryNavKey: "governance",
    tone: "cyan",
    image: "/assets/landing/homepage-carousel/09-modern-library-unsplash.webp",
    imagePosition: "62% center",
    alt: "现代图书馆与知识空间场景",
    infoTitle: "知识库治理",
    infoBody: "课程资料已完成清洗与审核",
    infoFoot: "来源可追溯 · 结构清晰",
  },
  {
    navKey: "governance",
    eyebrow: "知识图谱驱动",
    titleLines: ["让系统知道", "先学什么，", "再学什么"],
    subtitle: "知识节点、先修关系和薄弱点共同约束学习顺序，避免重复学习和盲目推进。",
    primaryText: "查看知识图谱",
    primaryTo: "/knowledge-graph",
    secondaryText: "理解核心能力",
    secondaryNavKey: "capability",
    tone: "green",
    image: "/assets/landing/homepage-carousel/10-digital-study-unsplash.webp",
    imagePosition: "66% center",
    alt: "数字化学习与知识连接的场景",
    infoTitle: "知识图谱",
    infoBody: "先修关系已连接",
    infoFoot: "路径将据此自动规划",
  },
  {
    navKey: "agents",
    eyebrow: "学习者画像",
    titleLines: ["画像来自", "真实学习行为，", "而不是静态问卷"],
    subtitle: "诊断、练习、资源完成状态和测评结果会回流更新掌握度，推动下一轮规划。",
    primaryText: "开始诊断",
    primaryTo: "/diagnosis",
    secondaryText: "查看学习路径",
    secondaryNavKey: "planning",
    tone: "gold",
    image: "/assets/landing/homepage-carousel/02-asian-student-laptop-pexels.webp",
    imagePosition: "68% center",
    alt: "学生在笔记本电脑前专注学习",
    infoTitle: "学习者画像",
    infoBody: "当前掌握度 72%",
    infoFoot: "待补强：梯度下降",
  },
  {
    navKey: "scenarios",
    eyebrow: "多 Agent 协同",
    titleLines: ["复杂智能过程，", "最终收束成", "清晰下一步"],
    subtitle: "诊断、检索、规划与资源生成协同工作，但学习者看到的是可执行、可理解的学习建议。",
    primaryText: "开始使用",
    primaryTo: "/register",
    secondaryText: "查看协作流程",
    secondaryNavKey: "agents",
    tone: "navy",
    image: "/assets/landing/homepage-carousel/04-collaborative-learning-pexels.webp",
    imagePosition: "60% center",
    alt: "多人协作进行学习讨论的场景",
    infoTitle: "多 Agent 协同",
    infoBody: "诊断、检索、规划已串联",
    infoFoot: "复杂过程收束为下一步",
  },
];

const activeIndex = ref(0);
const isPaused = ref(false);
const isHovered = ref(false);
const isDocumentHidden = ref(false);
const prefersReducedMotion = ref(false);
let timer: number | undefined;
let mediaQuery: MediaQueryList | undefined;
let onCarouselRequest: ((event: Event) => void) | undefined;

const trackStyle = computed(() => ({
  transform: `translate3d(-${activeIndex.value * 100}%, 0, 0)`,
}));

const shouldAutoplay = computed(
  () => !isPaused.value && !isHovered.value && !isDocumentHidden.value && !prefersReducedMotion.value,
);

function goTo(index: number) {
  activeIndex.value = (index + slides.length) % slides.length;
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("home-carousel-change", { detail: slides[activeIndex.value].navKey }));
  }
}

function goNext() {
  goTo(activeIndex.value + 1);
}

function goPrev() {
  goTo(activeIndex.value - 1);
}

function handleSecondaryAction(navKey: string) {
  const targetIndex = slides.findIndex((slide) => slide.navKey === navKey);
  if (targetIndex >= 0) goTo(targetIndex);
}

function clearTimer() {
  if (timer) {
    window.clearInterval(timer);
    timer = undefined;
  }
}

function startTimer() {
  clearTimer();
  if (!shouldAutoplay.value) return;
  timer = window.setInterval(goNext, AUTO_PLAY_DELAY);
}

function togglePause() {
  isPaused.value = !isPaused.value;
}

function handleMotionPreference(event: MediaQueryListEvent | MediaQueryList) {
  prefersReducedMotion.value = event.matches;
}

function handleVisibilityChange() {
  isDocumentHidden.value = document.hidden;
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    goPrev();
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    goNext();
  }
}

onMounted(() => {
  mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  handleMotionPreference(mediaQuery);
  mediaQuery.addEventListener("change", handleMotionPreference);
  document.addEventListener("visibilitychange", handleVisibilityChange);
  onCarouselRequest = (event: Event) => {
    const key = (event as CustomEvent<string>).detail;
    const index = slides.findIndex((slide) => slide.navKey === key);
    if (index >= 0) goTo(index);
  };
  window.addEventListener("home-carousel-go", onCarouselRequest);
  startTimer();
});

onBeforeUnmount(() => {
  clearTimer();
  mediaQuery?.removeEventListener("change", handleMotionPreference);
  document.removeEventListener("visibilitychange", handleVisibilityChange);
  if (onCarouselRequest) window.removeEventListener("home-carousel-go", onCarouselRequest);
});

watch([activeIndex, isPaused, isHovered, isDocumentHidden, prefersReducedMotion], startTimer);
</script>

<template>
  <section class="home-hero-carousel" aria-label="产品首页轮播海报" tabindex="0" @keydown="handleKeydown">
    <div class="home-hero-carousel__viewport" @mouseenter="isHovered = true" @mouseleave="isHovered = false">
      <div class="home-hero-carousel__track" :style="trackStyle">
        <article
          v-for="(slide, index) in slides"
          :key="slide.titleLines.join('')"
          class="home-hero-carousel__slide"
          :class="[`home-hero-carousel__slide--${slide.tone}`, { 'is-active': activeIndex === index }]"
          :aria-hidden="activeIndex !== index"
        >
          <div class="home-hero-carousel__copy">
            <span class="home-hero-carousel__eyebrow">
              <Sparkles :size="16" />
              {{ slide.eyebrow }}
            </span>
            <h1>
              <span v-for="line in slide.titleLines" :key="line">{{ line }}</span>
            </h1>
            <p>{{ slide.subtitle }}</p>
            <div class="home-hero-carousel__actions">
              <RouterLink :to="slide.primaryTo" class="button button-primary">
                {{ slide.primaryText }}
                <ArrowRight :size="17" />
              </RouterLink>
              <a
                :href="`#${slide.secondaryNavKey}`"
                class="button button-secondary"
                @click.prevent="handleSecondaryAction(slide.secondaryNavKey)"
              >{{ slide.secondaryText }}</a>
            </div>
          </div>

          <div class="home-hero-carousel__poster">
            <img
              class="home-hero-carousel__poster-image"
              :src="slide.image"
              :alt="activeIndex === index ? slide.alt : ''"
              decoding="async"
              :loading="index === 0 ? 'eager' : 'lazy'"
              :style="{ objectPosition: slide.imagePosition }"
            />
            <div class="home-hero-carousel__poster-overlay" />
            <div class="home-hero-carousel__info-card">
              <strong>{{ slide.infoTitle }}</strong>
              <span>{{ slide.infoBody }}</span>
              <small>{{ slide.infoFoot }}</small>
            </div>
          </div>
        </article>
      </div>

      <button class="home-hero-carousel__nav home-hero-carousel__nav--prev" type="button" aria-label="上一张" @click="goPrev">
        <ArrowLeft :size="20" />
      </button>
      <button class="home-hero-carousel__nav home-hero-carousel__nav--next" type="button" aria-label="下一张" @click="goNext">
        <ArrowRight :size="20" />
      </button>
    </div>

    <div class="home-hero-carousel__controls" aria-label="轮播控制">
      <button
        v-for="(_, index) in slides"
        :key="index"
        class="home-hero-carousel__dot"
        :class="{ 'is-active': activeIndex === index }"
        type="button"
        :aria-label="`切换到第 ${index + 1} 张海报`"
        :aria-current="activeIndex === index ? 'true' : undefined"
        @click="goTo(index)"
      />
      <button class="home-hero-carousel__pause" type="button" :aria-label="isPaused ? '继续轮播' : '暂停轮播'" @click="togglePause">
        <component :is="isPaused ? Play : Pause" :size="14" />
        <span>{{ isPaused ? "继续" : "暂停" }}</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.home-hero-carousel {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  width: min(92vw, 1680px);
  margin: 0 auto;
  padding: 22px 0 12px;
}

.home-hero-carousel__viewport {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  border: 1px solid rgba(190, 205, 224, 0.75);
  border-radius: 20px;
  background: linear-gradient(135deg, rgba(248, 251, 255, 0.98), rgba(236, 246, 255, 0.92));
  box-shadow: 0 18px 50px rgba(40, 75, 120, 0.1);
}

.home-hero-carousel__track {
  display: flex;
  width: 100%;
  height: 100%;
  transition: transform 0.48s cubic-bezier(0.22, 1, 0.36, 1);
  will-change: transform;
}

.home-hero-carousel__slide {
  position: relative;
  flex: 0 0 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.home-hero-carousel__slide::before {
  position: absolute;
  inset: 0;
  content: "";
  background: linear-gradient(
    90deg,
    #ffffff 0%,
    #f8fbff 40%,
    rgba(248, 251, 255, 0.88) 48%,
    rgba(248, 251, 255, 0.2) 64%,
    rgba(248, 251, 255, 0) 78%
  );
  pointer-events: none;
}

.home-hero-carousel__slide--cyan::before {
  background: linear-gradient(
    90deg,
    #ffffff 0%,
    #f7fcff 40%,
    rgba(247, 252, 255, 0.88) 48%,
    rgba(247, 252, 255, 0.2) 64%,
    rgba(247, 252, 255, 0) 78%
  );
}

.home-hero-carousel__slide--green::before {
  background: linear-gradient(
    90deg,
    #ffffff 0%,
    #f7fdfb 40%,
    rgba(247, 253, 251, 0.88) 48%,
    rgba(247, 253, 251, 0.2) 64%,
    rgba(247, 253, 251, 0) 78%
  );
}

.home-hero-carousel__slide--gold::before {
  background: linear-gradient(
    90deg,
    #ffffff 0%,
    #fffdf7 40%,
    rgba(255, 253, 247, 0.88) 48%,
    rgba(255, 253, 247, 0.2) 64%,
    rgba(255, 253, 247, 0) 78%
  );
}

.home-hero-carousel__slide--navy {
  background: linear-gradient(135deg, #f7fbff, #edf5ff 58%, #f5fbfb);
}

.home-hero-carousel__slide--navy::before {
  background: linear-gradient(
    90deg,
    #ffffff 0%,
    #f7fbff 40%,
    rgba(247, 251, 255, 0.88) 48%,
    rgba(247, 251, 255, 0.2) 64%,
    rgba(247, 251, 255, 0) 78%
  );
}

.home-hero-carousel__copy,
.home-hero-carousel__poster {
  position: relative;
  z-index: 1;
}

.home-hero-carousel__copy {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 3;
  display: flex;
  width: min(40%, 650px);
  height: 100%;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  padding: clamp(54px, 8vh, 96px) 0 clamp(92px, 11vh, 132px) clamp(32px, 5vw, 86px);
}

.home-hero-carousel__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #356ae6;
  font-size: 14px;
  font-weight: 800;
}

.home-hero-carousel h1 {
  max-width: 620px;
  margin: 20px 0 18px;
  color: #102746;
  font-family: "PingFang SC", "HarmonyOS Sans SC", "Noto Sans SC", "Microsoft YaHei", sans-serif;
  font-size: clamp(40px, 3vw, 60px);
  font-weight: 700;
  line-height: 1.12;
  letter-spacing: -0.025em;
  text-wrap: balance;
}

.home-hero-carousel h1 span {
  display: block;
}

.home-hero-carousel p {
  max-width: 620px;
  margin: 0;
  color: #62748d;
  font-size: clamp(16px, 1.15vw, 20px);
  line-height: 1.75;
}

.home-hero-carousel__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 30px;
}

.home-hero-carousel__poster {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 0;
  width: 68%;
  min-height: 0;
  overflow: hidden;
  border-radius: 0 20px 20px 0;
  background: transparent;
  pointer-events: none;
}

.home-hero-carousel__poster-image {
  display: block;
  width: 100%;
  height: 100%;
  min-height: 0;
  max-width: none;
  object-fit: cover;
  object-position: var(--hero-object-position, center center);
  filter: saturate(0.88) contrast(0.97) brightness(1.03);
  transform: scale(1.005);
  -webkit-mask-image: linear-gradient(
    90deg,
    transparent 0%,
    rgba(0, 0, 0, 0.04) 7%,
    rgba(0, 0, 0, 0.16) 14%,
    rgba(0, 0, 0, 0.38) 23%,
    rgba(0, 0, 0, 0.7) 34%,
    #000 46%,
    #000 100%
  );
  mask-image: linear-gradient(
    90deg,
    transparent 0%,
    rgba(0, 0, 0, 0.04) 7%,
    rgba(0, 0, 0, 0.16) 14%,
    rgba(0, 0, 0, 0.38) 23%,
    rgba(0, 0, 0, 0.7) 34%,
    #000 46%,
    #000 100%
  );
  -webkit-mask-repeat: no-repeat;
  mask-repeat: no-repeat;
  -webkit-mask-size: 100% 100%;
  mask-size: 100% 100%;
  transition: opacity 560ms ease, transform 760ms cubic-bezier(0.22, 1, 0.36, 1);
}

.home-hero-carousel__poster-overlay {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(
      90deg,
      #fbfcff 0%,
      #fbfcff 9%,
      rgba(251, 252, 255, 0.92) 22%,
      rgba(251, 252, 255, 0.56) 36%,
      rgba(251, 252, 255, 0.12) 52%,
      rgba(251, 252, 255, 0) 62%
    ),
    linear-gradient(180deg, rgba(255, 255, 255, 0.02), rgba(14, 36, 68, 0.08));
  pointer-events: none;
}

.home-hero-carousel__slide:not(.is-active) .home-hero-carousel__poster-image {
  opacity: 0;
  transform: scale(1.018);
}

.home-hero-carousel__slide.is-active .home-hero-carousel__poster-image {
  opacity: 1;
  transform: scale(1);
}

.home-hero-carousel__info-card {
  position: absolute;
  right: 22px;
  bottom: 22px;
  z-index: 2;
  display: grid;
  gap: 4px;
  max-width: 300px;
  padding: 14px 15px 13px;
  color: #173151;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(223, 232, 243, 0.92);
  border-radius: 16px;
  box-shadow: 0 12px 28px rgba(44, 67, 98, 0.12);
  backdrop-filter: blur(6px);
}

.home-hero-carousel__info-card strong {
  font-size: 14px;
  font-weight: 800;
}

.home-hero-carousel__info-card span {
  font-size: 18px;
  font-weight: 700;
  line-height: 1.35;
}

.home-hero-carousel__info-card small {
  color: #64748d;
  font-size: 12px;
  font-weight: 700;
}

.home-hero-carousel__nav {
  position: absolute;
  top: 50%;
  z-index: 3;
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  color: #356ae6;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(207, 224, 255, 0.9);
  border-radius: 999px;
  box-shadow: 0 12px 26px rgba(39, 72, 112, 0.08);
  transform: translateY(-50%);
}

.home-hero-carousel__nav--prev {
  left: 24px;
}

.home-hero-carousel__nav--next {
  right: 24px;
}

.home-hero-carousel__controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-top: 18px;
}

.home-hero-carousel__dot {
  width: 8px;
  height: 8px;
  padding: 0;
  background: #cbd5e1;
  border: 0;
  border-radius: 999px;
  transition: width 0.22s ease, background-color 0.22s ease;
}

.home-hero-carousel__dot.is-active {
  width: 38px;
  background: #356ae6;
}

.home-hero-carousel__pause {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  margin-left: 8px;
  padding: 0 10px;
  color: #5f718a;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid #dfe8f3;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

@media (max-width: 1199px) and (min-width: 761px) {
  .home-hero-carousel__slide {
    height: 100%;
  }

  .home-hero-carousel__copy {
    width: 48%;
    padding-left: clamp(28px, 5vw, 56px);
  }

  .home-hero-carousel__copy {
    padding-top: 44px;
    padding-bottom: 78px;
  }

  .home-hero-carousel__poster {
    width: 62%;
    border-radius: 0 20px 20px 0;
  }

  .home-hero-carousel__poster-image {
    height: 100%;
    min-height: 0;
  }
}

@media (max-width: 760px) {
  .home-hero-carousel {
    width: min(100% - 24px, 1680px);
    padding-top: 16px;
  }

  .home-hero-carousel__slide {
    display: grid;
    height: auto;
    gap: 22px;
    padding: 28px 18px 24px;
  }

  .home-hero-carousel__copy {
    position: relative;
    width: 100%;
    height: auto;
    padding: 0;
  }

  .home-hero-carousel__poster {
    position: relative;
    top: auto;
    right: auto;
    bottom: auto;
    width: 100%;
    height: 250px;
    border-radius: 16px;
  }

  .home-hero-carousel h1 {
    max-width: 100%;
    margin: 16px 0 14px;
    font-size: clamp(32px, 9vw, 40px);
  }

  .home-hero-carousel p {
    font-size: 15px;
    line-height: 1.72;
  }

  .home-hero-carousel__actions {
    margin-top: 22px;
  }

  .home-hero-carousel__info-card {
    right: 16px;
    bottom: 16px;
    max-width: calc(100% - 32px);
  }

  .home-hero-carousel__info-card span {
    font-size: 16px;
  }

  .home-hero-carousel__nav {
    top: auto;
    bottom: 18px;
    width: 40px;
    height: 40px;
    transform: none;
  }
}

@media (max-width: 460px) {
  .home-hero-carousel__slide {
    padding-inline: 16px;
  }

  .home-hero-carousel__poster,
  .home-hero-carousel__poster-image {
    height: 250px;
    min-height: 0;
  }

  .home-hero-carousel__poster-image {
    -webkit-mask-image: linear-gradient(
      180deg,
      #000 0%,
      #000 66%,
      rgba(0, 0, 0, 0.5) 82%,
      transparent 100%
    );
    mask-image: linear-gradient(
      180deg,
      #000 0%,
      #000 66%,
      rgba(0, 0, 0, 0.5) 82%,
      transparent 100%
    );
  }

  .home-hero-carousel__poster-overlay {
    background: linear-gradient(
      180deg,
      rgba(251, 252, 255, 0) 0%,
      rgba(251, 252, 255, 0) 62%,
      rgba(251, 252, 255, 0.42) 84%,
      #fbfcff 100%
    );
  }

  .home-hero-carousel__poster {
    height: 250px;
    border-radius: 16px;
  }

  .home-hero-carousel__info-card span {
    font-size: 15px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .home-hero-carousel__track,
  .home-hero-carousel__dot,
  .home-hero-carousel__poster-image {
    transition: none !important;
  }
}

@supports not ((mask-image: linear-gradient(#000, transparent)) or (-webkit-mask-image: linear-gradient(#000, transparent))) {
  .home-hero-carousel__poster-image {
    -webkit-mask-image: none;
    mask-image: none;
  }

  .home-hero-carousel__poster-overlay {
    background: linear-gradient(
      90deg,
      #fbfcff 0%,
      #fbfcff 34%,
      rgba(251, 252, 255, 0.96) 42%,
      rgba(251, 252, 255, 0.68) 50%,
      rgba(251, 252, 255, 0) 64%
    );
  }
}
</style>
