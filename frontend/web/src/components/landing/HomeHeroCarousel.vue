<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import { ArrowLeft, ArrowRight, Pause, Play, Sparkles } from "lucide-vue-next";

interface BannerSlide {
  eyebrow: string;
  title: string[];
  subtitle: string;
  primaryText: string;
  primaryTo: string;
  secondaryText: string;
  secondaryHref: string;
  tone: "blue" | "cyan" | "green" | "gold" | "navy";
  posterTitle: string;
  posterMeta: string;
  nodes: string[];
  stats: Array<{ value: string; label: string }>;
}

const AUTO_PLAY_DELAY = 5000;

const slides: BannerSlide[] = [
  {
    eyebrow: "织知成径 · AI 辅助学习平台",
    title: ["从课程知识库，", "到每个人的", "智能学习路径"],
    subtitle: "将课程资料、知识图谱与学习反馈连接起来，为每一次学习找到更合适的下一步。",
    primaryText: "开始学习",
    primaryTo: "/register",
    secondaryText: "了解平台如何工作",
    secondaryHref: "#workflow",
    tone: "blue",
    posterTitle: "知识正在被织成路径",
    posterMeta: "课程资料 → 学情理解 → 个性化规划",
    nodes: ["课程资料", "知识关系", "学习状态", "路径规划", "反馈回流"],
    stats: [
      { value: "72%", label: "当前掌握度" },
      { value: "3项", label: "待补强知识" },
      { value: "实时", label: "反馈更新" },
    ],
  },
  {
    eyebrow: "课程知识库治理",
    title: ["把分散课程资料，", "整理成可追溯的", "知识资产"],
    subtitle: "教材、课件、讲义与练习不再散落，平台会保留来源、审核状态和知识归属。",
    primaryText: "进入课程中心",
    primaryTo: "/courses",
    secondaryText: "查看知识库治理",
    secondaryHref: "#governance",
    tone: "cyan",
    posterTitle: "课程资料汇入知识网络",
    posterMeta: "机器学习导论 · 第 2 章 · 已审核来源",
    nodes: ["资料清洗", "知识切分", "证据审核", "资源索引", "持续维护"],
    stats: [
      { value: "135", label: "学习资源" },
      { value: "14", label: "知识点" },
      { value: "6章", label: "课程结构" },
    ],
  },
  {
    eyebrow: "知识图谱驱动",
    title: ["让系统知道", "先学什么，", "再学什么"],
    subtitle: "知识节点、先修关系和薄弱点共同约束学习顺序，避免重复学习和盲目推进。",
    primaryText: "查看知识图谱",
    primaryTo: "/knowledge-graph",
    secondaryText: "理解核心能力",
    secondaryHref: "#capability",
    tone: "green",
    posterTitle: "知识关系形成学习地图",
    posterMeta: "线性回归 → 损失函数 → 梯度下降",
    nodes: ["线性回归", "损失函数", "梯度下降", "单元测评", "掌握更新"],
    stats: [
      { value: "图谱", label: "先修关系" },
      { value: "诊断", label: "定位薄弱点" },
      { value: "路径", label: "动态生成" },
    ],
  },
  {
    eyebrow: "学习者画像",
    title: ["画像来自", "真实学习行为，", "而不是静态问卷"],
    subtitle: "诊断、练习、资源完成状态和测评结果会回流更新掌握度，推动下一轮规划。",
    primaryText: "开始诊断",
    primaryTo: "/diagnosis",
    secondaryText: "查看学习路径",
    secondaryHref: "#planning",
    tone: "gold",
    posterTitle: "当前学习状态成为路径锚点",
    posterMeta: "当前掌握度 72% · 待补强：梯度下降",
    nodes: ["学习目标", "掌握趋势", "薄弱知识", "推荐练习", "反馈修正"],
    stats: [
      { value: "画像", label: "理解学习者" },
      { value: "下一步", label: "明确任务" },
      { value: "闭环", label: "持续优化" },
    ],
  },
  {
    eyebrow: "多 Agent 协同",
    title: ["复杂智能过程，", "最终收束成", "清晰下一步"],
    subtitle: "诊断、检索、规划与资源生成协同工作，但学习者看到的是可执行、可理解的学习建议。",
    primaryText: "开始使用",
    primaryTo: "/register",
    secondaryText: "查看协作流程",
    secondaryHref: "#agents",
    tone: "navy",
    posterTitle: "智能运行服务学习决策",
    posterMeta: "诊断 Agent · 检索 Agent · 规划 Agent",
    nodes: ["诊断", "检索", "规划", "生成", "反馈"],
    stats: [
      { value: "AI", label: "辅助决策" },
      { value: "证据", label: "来源优先" },
      { value: "任务", label: "落到行动" },
    ],
  },
];

const activeIndex = ref(0);
const isPaused = ref(false);
const prefersReducedMotion = ref(false);
let timer: number | undefined;
let mediaQuery: MediaQueryList | undefined;

const trackStyle = computed(() => ({
  transform: `translate3d(-${activeIndex.value * 100}%, 0, 0)`,
}));

function goTo(index: number) {
  activeIndex.value = (index + slides.length) % slides.length;
}

function goNext() {
  goTo(activeIndex.value + 1);
}

function goPrev() {
  goTo(activeIndex.value - 1);
}

function clearTimer() {
  if (timer) {
    window.clearInterval(timer);
    timer = undefined;
  }
}

function startTimer() {
  clearTimer();
  if (isPaused.value || prefersReducedMotion.value) return;
  timer = window.setInterval(goNext, AUTO_PLAY_DELAY);
}

function togglePause() {
  isPaused.value = !isPaused.value;
}

function handleMotionPreference(event: MediaQueryListEvent | MediaQueryList) {
  prefersReducedMotion.value = event.matches;
}

onMounted(() => {
  mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  handleMotionPreference(mediaQuery);
  mediaQuery.addEventListener("change", handleMotionPreference);
  startTimer();
});

onBeforeUnmount(() => {
  clearTimer();
  mediaQuery?.removeEventListener("change", handleMotionPreference);
});

watch([activeIndex, isPaused, prefersReducedMotion], startTimer);
</script>

<template>
  <section class="home-hero-carousel" aria-label="产品首页轮播海报">
    <div class="home-hero-carousel__viewport">
      <div class="home-hero-carousel__track" :style="trackStyle">
        <article
          v-for="(slide, index) in slides"
          :key="slide.title.join('')"
          class="home-hero-carousel__slide"
          :class="`home-hero-carousel__slide--${slide.tone}`"
          :aria-hidden="activeIndex !== index"
        >
          <div class="home-hero-carousel__copy">
            <span class="home-hero-carousel__eyebrow">
              <Sparkles :size="16" />
              {{ slide.eyebrow }}
            </span>
            <h1>
              <span v-for="line in slide.title" :key="line">{{ line }}</span>
            </h1>
            <p>{{ slide.subtitle }}</p>
            <div class="home-hero-carousel__actions">
              <RouterLink :to="slide.primaryTo" class="button button-primary">
                {{ slide.primaryText }}
                <ArrowRight :size="17" />
              </RouterLink>
              <a :href="slide.secondaryHref" class="button button-secondary">{{ slide.secondaryText }}</a>
            </div>
          </div>

          <div class="home-hero-carousel__poster" aria-hidden="true">
            <div class="home-hero-carousel__poster-header">
              <span>{{ slide.posterTitle }}</span>
              <small>{{ slide.posterMeta }}</small>
            </div>

            <svg viewBox="0 0 700 440" role="presentation">
              <defs>
                <linearGradient :id="`banner-thread-${index}`" x1="8%" y1="18%" x2="92%" y2="82%">
                  <stop offset="0%" stop-color="#78b7ff" />
                  <stop offset="58%" stop-color="#2f6fec" />
                  <stop offset="100%" stop-color="#18a7a0" />
                </linearGradient>
              </defs>
              <path
                class="poster-thread poster-thread--main"
                :stroke="`url(#banner-thread-${index})`"
                d="M62 236C130 132 226 110 318 178C412 248 500 250 638 128"
              />
              <path
                class="poster-thread poster-thread--secondary"
                :stroke="`url(#banner-thread-${index})`"
                d="M88 312C182 270 264 306 342 350C448 408 552 374 622 298"
              />
              <path class="poster-thread poster-thread--feedback" d="M548 318C584 376 514 424 428 402C350 382 312 336 274 286" />

              <g class="poster-node-group">
                <circle cx="104" cy="198" r="11" />
                <circle cx="214" cy="128" r="13" />
                <circle cx="326" cy="178" r="15" />
                <circle cx="454" cy="230" r="13" />
                <circle cx="588" cy="162" r="16" />
                <circle cx="202" cy="302" r="10" />
                <circle cx="348" cy="354" r="12" />
                <circle cx="502" cy="374" r="11" />
              </g>
              <g class="poster-document">
                <path d="M86 94h116l34 34v128H86z" />
                <path d="M202 94v34h34" />
                <path d="M118 150h76M118 180h92M118 210h62" />
              </g>
              <g class="poster-beacon">
                <circle cx="326" cy="178" r="38" />
                <circle cx="326" cy="178" r="18" />
              </g>
            </svg>

            <div class="home-hero-carousel__poster-footer">
              <span v-for="node in slide.nodes" :key="`${slide.title.join('')}-${node}`">{{ node }}</span>
            </div>

            <div class="home-hero-carousel__stats">
              <span v-for="stat in slide.stats" :key="`${slide.title.join('')}-${stat.label}`">
                <strong>{{ stat.value }}</strong>
                <small>{{ stat.label }}</small>
              </span>
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

    <p class="home-hero-carousel__next-preview">从课程资源到个体路径</p>
  </section>
</template>

<style scoped>
.home-hero-carousel {
  width: min(1360px, calc(100% - 48px));
  margin: 0 auto;
  padding: 28px 0 20px;
}

.home-hero-carousel__viewport {
  position: relative;
  min-height: min(620px, calc(100svh - 228px));
  overflow: hidden;
  border: 1px solid rgba(213, 226, 242, 0.86);
  border-radius: 28px;
  background:
    radial-gradient(circle at 72% 28%, rgba(87, 170, 255, 0.18), transparent 24%),
    radial-gradient(circle at 86% 78%, rgba(24, 167, 160, 0.12), transparent 26%),
    linear-gradient(135deg, rgba(248, 252, 255, 0.98), rgba(236, 246, 255, 0.92));
  box-shadow: 0 24px 70px rgba(39, 72, 112, 0.12);
}

.home-hero-carousel__track {
  display: flex;
  width: 100%;
  min-height: inherit;
  transition: transform 0.62s cubic-bezier(0.22, 1, 0.36, 1);
  will-change: transform;
}

.home-hero-carousel__slide {
  position: relative;
  display: grid;
  flex: 0 0 100%;
  grid-template-columns: minmax(490px, 0.92fr) minmax(500px, 1.08fr);
  gap: clamp(28px, 4vw, 62px);
  align-items: center;
  min-width: 0;
  padding: clamp(42px, 5vw, 70px) clamp(50px, 6vw, 86px);
  overflow: hidden;
}

.home-hero-carousel__slide::before {
  position: absolute;
  inset: 0;
  content: "";
  background:
    linear-gradient(90deg, rgba(249, 252, 255, 0.94), rgba(249, 252, 255, 0.46) 54%, rgba(249, 252, 255, 0.08)),
    radial-gradient(circle at 16% 84%, rgba(47, 111, 236, 0.08), transparent 30%);
  pointer-events: none;
}

.home-hero-carousel__slide--cyan::before {
  background:
    linear-gradient(90deg, rgba(249, 252, 255, 0.95), rgba(235, 251, 255, 0.46) 54%, rgba(232, 252, 248, 0.1)),
    radial-gradient(circle at 78% 22%, rgba(6, 182, 212, 0.13), transparent 30%);
}

.home-hero-carousel__slide--green::before {
  background:
    linear-gradient(90deg, rgba(249, 252, 255, 0.95), rgba(238, 253, 248, 0.42) 56%, rgba(230, 250, 243, 0.1)),
    radial-gradient(circle at 76% 72%, rgba(24, 167, 160, 0.12), transparent 30%);
}

.home-hero-carousel__slide--gold::before {
  background:
    linear-gradient(90deg, rgba(255, 253, 248, 0.95), rgba(249, 252, 255, 0.44) 56%, rgba(255, 247, 225, 0.08)),
    radial-gradient(circle at 74% 68%, rgba(245, 158, 11, 0.1), transparent 30%);
}

.home-hero-carousel__slide--navy {
  background:
    radial-gradient(circle at 78% 24%, rgba(36, 213, 188, 0.18), transparent 28%),
    linear-gradient(135deg, #0c2342, #154575 58%, #0a2e4f);
}

.home-hero-carousel__slide--navy::before {
  background:
    linear-gradient(90deg, rgba(7, 26, 53, 0.78), rgba(11, 46, 83, 0.34) 54%, rgba(7, 26, 53, 0.08)),
    radial-gradient(circle at 16% 82%, rgba(125, 184, 255, 0.16), transparent 30%);
}

.home-hero-carousel__copy,
.home-hero-carousel__poster {
  position: relative;
  z-index: 1;
}

.home-hero-carousel__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #356ae6;
  font-size: 14px;
  font-weight: 800;
}

.home-hero-carousel__slide--navy .home-hero-carousel__eyebrow,
.home-hero-carousel__slide--navy h1,
.home-hero-carousel__slide--navy p {
  color: #fff;
}

.home-hero-carousel h1 {
  max-width: 13ch;
  margin: 20px 0 18px;
  color: #12223c;
  font-family: "PingFang SC", "HarmonyOS Sans SC", "Noto Sans SC", "Microsoft YaHei", sans-serif;
  font-size: clamp(44px, 4.4vw, 62px);
  font-weight: 760;
  line-height: 1.1;
  letter-spacing: 0;
  text-wrap: balance;
}

.home-hero-carousel h1 span {
  display: block;
}

.home-hero-carousel p {
  max-width: 590px;
  margin: 0;
  color: #5f718a;
  font-size: clamp(16px, 1.25vw, 19px);
  line-height: 1.85;
}

.home-hero-carousel__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 32px;
}

.home-hero-carousel__poster {
  min-height: 420px;
  overflow: hidden;
  border: 1px solid rgba(220, 229, 241, 0.74);
  border-radius: 26px;
  background:
    radial-gradient(circle at 48% 32%, rgba(255, 255, 255, 0.94), transparent 28%),
    radial-gradient(circle at 72% 70%, rgba(25, 168, 143, 0.13), transparent 28%),
    rgba(255, 255, 255, 0.42);
}

.home-hero-carousel__poster-header {
  position: absolute;
  top: 24px;
  left: 26px;
  z-index: 2;
  display: grid;
  gap: 6px;
}

.home-hero-carousel__poster-header span {
  color: #18345c;
  font-size: 18px;
  font-weight: 800;
}

.home-hero-carousel__poster-header small {
  color: #60758e;
  font-size: 12px;
  font-weight: 700;
}

.home-hero-carousel__poster svg {
  display: block;
  width: 100%;
  height: 100%;
  min-height: 420px;
}

.poster-thread {
  fill: none;
  stroke-width: 4;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 9 11;
  animation: hero-banner-thread 20s linear infinite;
}

.poster-thread--secondary {
  stroke-width: 2.4;
  opacity: 0.62;
}

.poster-thread--feedback {
  stroke: rgba(24, 167, 160, 0.55);
  stroke-width: 2.4;
  opacity: 0.72;
}

.poster-node-group circle {
  fill: #fff;
  stroke: #2f6fec;
  stroke-width: 4;
  filter: drop-shadow(0 10px 16px rgba(47, 111, 236, 0.16));
}

.poster-node-group circle:nth-child(3n) {
  stroke: #18a7a0;
}

.poster-document path {
  fill: rgba(255, 255, 255, 0.82);
  stroke: rgba(125, 184, 255, 0.58);
  stroke-width: 2.2;
}

.poster-document path:nth-child(n + 2) {
  fill: none;
  stroke: rgba(47, 111, 236, 0.55);
}

.poster-beacon circle:first-child {
  fill: rgba(47, 111, 236, 0.08);
  stroke: rgba(47, 111, 236, 0.22);
  stroke-width: 2;
}

.poster-beacon circle:last-child {
  fill: #2f6fec;
  stroke: #fff;
  stroke-width: 5;
}

.home-hero-carousel__poster-footer {
  position: absolute;
  right: 24px;
  bottom: 24px;
  left: 24px;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.home-hero-carousel__poster-footer span {
  padding: 8px 12px;
  color: #4f6480;
  background: rgba(255, 255, 255, 0.76);
  border: 1px solid rgba(220, 229, 241, 0.9);
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.home-hero-carousel__stats {
  position: absolute;
  right: 24px;
  top: 24px;
  z-index: 2;
  display: flex;
  gap: 10px;
}

.home-hero-carousel__stats span {
  min-width: 88px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.74);
  border: 1px solid rgba(220, 229, 241, 0.88);
  border-radius: 14px;
}

.home-hero-carousel__stats strong,
.home-hero-carousel__stats small {
  display: block;
}

.home-hero-carousel__stats strong {
  color: #1c3760;
  font-size: 16px;
}

.home-hero-carousel__stats small {
  margin-top: 4px;
  color: #6b7f98;
  font-size: 12px;
}

.home-hero-carousel__nav {
  position: absolute;
  top: 50%;
  z-index: 3;
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  color: #356ae6;
  background: rgba(255, 255, 255, 0.84);
  border: 1px solid rgba(207, 224, 255, 0.9);
  border-radius: 999px;
  box-shadow: 0 12px 26px rgba(39, 72, 112, 0.1);
  transform: translateY(-50%);
}

.home-hero-carousel__nav--prev {
  left: 20px;
}

.home-hero-carousel__nav--next {
  right: 20px;
}

.home-hero-carousel__controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  margin-top: 18px;
}

.home-hero-carousel__dot {
  width: 9px;
  height: 9px;
  padding: 0;
  background: #cbd5e1;
  border: 0;
  border-radius: 999px;
  transition: width 0.22s ease, background-color 0.22s ease;
}

.home-hero-carousel__dot.is-active {
  width: 34px;
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
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid #dfe8f3;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.home-hero-carousel__next-preview {
  margin: 14px 0 0;
  color: #6b7f98;
  font-size: 14px;
  font-weight: 700;
  text-align: center;
}

@keyframes hero-banner-thread {
  from {
    stroke-dashoffset: 0;
  }

  to {
    stroke-dashoffset: -120;
  }
}

@media (max-width: 1100px) {
  .home-hero-carousel__slide {
    grid-template-columns: 1fr;
    padding: 40px 32px 32px;
  }

  .home-hero-carousel__viewport {
    min-height: auto;
  }

  .home-hero-carousel__poster,
  .home-hero-carousel__poster svg {
    min-height: 330px;
  }
}

@media (max-width: 760px) {
  .home-hero-carousel {
    width: min(100% - 24px, 1360px);
    padding-top: 16px;
  }

  .home-hero-carousel__track {
    align-items: stretch;
  }

  .home-hero-carousel__slide {
    gap: 24px;
    padding: 28px 18px 24px;
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
    margin-top: 24px;
  }

  .home-hero-carousel__actions {
    display: grid;
    grid-template-columns: 1fr;
  }

  .home-hero-carousel__poster-header {
    top: 18px;
    right: 18px;
    left: 18px;
  }

  .home-hero-carousel__poster-header span {
    font-size: 16px;
  }

  .home-hero-carousel__stats {
    position: absolute;
    top: auto;
    right: 18px;
    bottom: 58px;
    left: 18px;
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-start;
    margin: 0;
  }

  .home-hero-carousel__stats span {
    min-width: 0;
    padding: 7px 9px;
  }

  .home-hero-carousel__poster-footer {
    left: 18px;
    right: 18px;
    justify-content: flex-start;
  }

  .home-hero-carousel__nav {
    top: auto;
    bottom: 22px;
    width: 40px;
    height: 40px;
  }
}

@media (max-width: 460px) {
  .home-hero-carousel__slide {
    padding-inline: 16px;
  }

  .home-hero-carousel__poster,
  .home-hero-carousel__poster svg {
    min-height: 250px;
  }

  .home-hero-carousel__poster-footer span {
    font-size: 11px;
  }

  .home-hero-carousel__stats small {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .home-hero-carousel__track,
  .home-hero-carousel__dot,
  .poster-thread {
    animation: none !important;
    transition: none !important;
  }
}
</style>
