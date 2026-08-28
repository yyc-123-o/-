<script setup lang="ts">
import { onBeforeUnmount, onMounted } from "vue";
import { ArrowRight, BookOpenText, Compass, Sparkles } from "lucide-vue-next";
import { RouterLink } from "vue-router";

const topLinks = [
  { label: "学习方式", href: "#learn" },
  { label: "个性化路径", href: "#path" },
  { label: "AI 学习助手", href: "#assistant" },
  { label: "关于知径", href: "#about" },
];

const diagnosisTags = ["基础信息", "知识水平", "学习目标"];
const footerLinks = ["产品介绍", "使用帮助", "联系我们"];

let observer: IntersectionObserver | null = null;

onMounted(() => {
  const items = document.querySelectorAll<HTMLElement>("[data-reveal]");
  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer?.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.18 },
  );
  items.forEach((item) => observer?.observe(item));
});

onBeforeUnmount(() => observer?.disconnect());
</script>

<template>
  <div class="landing-page">
    <header class="landing-header">
      <RouterLink to="/" class="landing-brand" aria-label="知径首页">
        <span class="landing-mark">知</span>
        <span>
          <strong>知径</strong>
          <small>AI 个性化学习平台</small>
        </span>
      </RouterLink>
      <nav class="landing-nav" aria-label="主导航">
        <a v-for="item in topLinks" :key="item.href" :href="item.href">{{ item.label }}</a>
      </nav>
      <div class="landing-actions">
        <RouterLink to="/dashboard" class="button button-quiet landing-link-button">登录</RouterLink>
        <RouterLink to="/diagnosis" class="button button-primary">开始体验 <ArrowRight :size="16" /></RouterLink>
      </div>
    </header>

    <main class="landing-main">
      <section class="landing-hero" data-reveal>
        <div class="landing-copy">
          <span class="eyebrow landing-eyebrow">AI PERSONALIZED LEARNING</span>
          <h1>从了解自己开始，找到适合你的学习路径。</h1>
          <p>
            知径通过学情诊断、知识图谱和 AI 学习助手，帮助每一位学习者明确自己的学习状态，并持续获得下一步学习建议。
          </p>
          <div class="landing-actions-row">
            <RouterLink to="/diagnosis" class="button button-primary button-large">开始学习诊断 <ArrowRight :size="16" /></RouterLink>
            <a class="button button-secondary button-large" href="#about">了解知径</a>
          </div>
          <div class="landing-signals">
            <span><BookOpenText :size="14" /> 学习起点</span>
            <span><Compass :size="14" /> 学习路径</span>
            <span><Sparkles :size="14" /> AI 辅导</span>
          </div>
        </div>
        <div class="hero-art" aria-hidden="true">
          <svg viewBox="0 0 720 560" role="img">
            <defs>
              <linearGradient id="heroGlow" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#eef5ff" />
                <stop offset="100%" stop-color="#dff6ff" />
              </linearGradient>
              <linearGradient id="routeBlue" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#2f6fec" />
                <stop offset="100%" stop-color="#0b91ac" />
              </linearGradient>
            </defs>
            <circle cx="230" cy="220" r="160" fill="url(#heroGlow)" />
            <circle cx="490" cy="112" r="18" fill="#c7eff7" class="float-slow" />
            <circle cx="568" cy="178" r="10" fill="#d7d0ff" class="float-slower" />
            <circle cx="132" cy="430" r="14" fill="#d7e7ff" class="float-slow" />
            <path d="M158 385 C212 320 284 304 338 296 C416 283 486 230 542 155" fill="none" stroke="url(#routeBlue)" stroke-width="10" stroke-linecap="round" class="route-line" />
            <path d="M318 305 C333 289 354 286 371 294" fill="none" stroke="#b7cdf8" stroke-width="6" stroke-linecap="round" />
            <g class="node-float">
              <circle cx="166" cy="386" r="22" fill="#fff" stroke="#2f6fec" stroke-width="4" />
              <circle cx="166" cy="386" r="9" fill="#2f6fec" />
            </g>
            <g class="node-float delay-one">
              <circle cx="314" cy="316" r="24" fill="#fff" stroke="#0b91ac" stroke-width="4" />
              <circle cx="314" cy="316" r="10" fill="#0b91ac" />
            </g>
            <g class="node-float delay-two">
              <circle cx="476" cy="232" r="24" fill="#fff" stroke="#7856d9" stroke-width="4" />
              <circle cx="476" cy="232" r="10" fill="#7856d9" />
            </g>
            <g class="node-float delay-three">
              <circle cx="556" cy="166" r="26" fill="#fff" stroke="#1da35f" stroke-width="4" />
              <circle cx="556" cy="166" r="11" fill="#1da35f" />
            </g>
            <path d="M354 236 C341 248 335 266 336 288" fill="none" stroke="#d7e7ff" stroke-width="8" stroke-linecap="round" />
            <rect x="220" y="168" rx="28" ry="28" width="158" height="118" fill="#fff" stroke="#e1ebfa" />
            <path d="M258 236 L301 196 L344 236 L301 274 Z" fill="#f3b16f" opacity=".85" />
            <circle cx="301" cy="226" r="21" fill="#0f243d" opacity=".92" />
            <path d="M300 252 C286 276 269 288 251 296" fill="none" stroke="#0f243d" stroke-width="6" stroke-linecap="round" />
            <path d="M314 252 C330 270 347 284 366 294" fill="none" stroke="#0f243d" stroke-width="6" stroke-linecap="round" />
            <rect x="392" y="320" width="160" height="94" rx="24" fill="#fff" stroke="#dfe8f3" />
            <rect x="416" y="345" width="56" height="14" rx="7" fill="#2f6fec" />
            <rect x="416" y="368" width="96" height="14" rx="7" fill="#d6e6ff" />
            <rect x="416" y="391" width="78" height="14" rx="7" fill="#e8fbf4" />
            <path d="M590 286 h42 a14 14 0 0 1 14 14 v32 a14 14 0 0 1 -14 14 h-12 l-14 16 v-16 h-16 a14 14 0 0 1 -14 -14 v-32 a14 14 0 0 1 14 -14 z" fill="#f4d3ff" />
            <circle cx="611" cy="311" r="8" fill="#172a43" />
            <path d="M625 306 q10 10 0 20" fill="none" stroke="#172a43" stroke-width="4" stroke-linecap="round" />
          </svg>
        </div>
      </section>

      <section id="learn" class="landing-section section-split" data-reveal>
        <div class="section-visual section-soft">
          <svg viewBox="0 0 560 460" role="img" aria-hidden="true">
            <rect x="118" y="100" width="250" height="176" rx="30" fill="#fff" stroke="#dae7f7" />
            <rect x="154" y="134" width="84" height="22" rx="11" fill="#eaf1ff" />
            <rect x="154" y="170" width="156" height="18" rx="9" fill="#dfe8f3" />
            <rect x="154" y="200" width="132" height="18" rx="9" fill="#edf7fc" />
            <circle cx="406" cy="158" r="84" fill="#eef5ff" />
            <circle cx="406" cy="158" r="48" fill="none" stroke="#2f6fec" stroke-width="12" stroke-dasharray="210 40" />
            <circle cx="406" cy="158" r="32" fill="#fff" stroke="#0b91ac" stroke-width="10" />
            <path d="M376 172 l30 -28 l30 28" fill="none" stroke="#0b91ac" stroke-width="10" stroke-linecap="round" stroke-linejoin="round" />
            <circle cx="182" cy="320" r="18" fill="#d7e7ff" />
            <circle cx="282" cy="320" r="18" fill="#d7d0ff" />
            <circle cx="382" cy="320" r="18" fill="#dff6ef" />
            <path d="M184 320 h172" stroke="#b7cdf8" stroke-width="6" stroke-linecap="round" stroke-dasharray="10 16" />
          </svg>
        </div>
        <div class="section-copy">
          <span class="section-kicker">科学诊断</span>
          <h2>先了解你的学习状态</h2>
          <p>
            知径会通过基础信息、课程自评和自适应测试，识别你已经掌握的知识，以及需要重点提升的内容。
          </p>
          <div class="mini-tags">
            <span v-for="item in diagnosisTags" :key="item">{{ item }}</span>
          </div>
        </div>
      </section>

      <section id="path" class="landing-section section-split section-tinted" data-reveal>
        <div class="section-copy">
          <span class="section-kicker">个性化路径</span>
          <h2>每个人，都应该有自己的学习路径</h2>
          <p>
            从基础知识到实践应用，知径会根据掌握度与先修关系，为你生成清晰、连续、可调整的学习路线。
          </p>
        </div>
        <div class="path-art">
          <div class="path-column">
            <div class="path-node done">基础知识</div>
            <div class="path-line" />
            <div class="path-node current">核心概念</div>
            <div class="path-line" />
            <div class="path-node waiting">实践应用</div>
            <div class="path-line" />
            <div class="path-node blocked">综合能力</div>
          </div>
          <div class="path-note">
            <strong>学习图谱</strong>
            <p>已掌握 · 学习中 · 待学习 · 被先修知识阻塞</p>
          </div>
        </div>
      </section>

      <section id="assistant" class="landing-section section-split" data-reveal>
        <div class="assistant-art">
          <svg viewBox="0 0 480 420" role="img" aria-hidden="true">
            <circle cx="200" cy="196" r="104" fill="#eef5ff" />
            <circle cx="200" cy="196" r="72" fill="#fff" stroke="#dbe7f8" stroke-width="2" />
            <circle cx="182" cy="182" r="12" fill="#2f6fec" />
            <circle cx="218" cy="182" r="12" fill="#0b91ac" />
            <path d="M180 216 q20 20 40 0" fill="none" stroke="#172a43" stroke-width="6" stroke-linecap="round" />
            <circle cx="336" cy="120" r="28" fill="#f1edff" />
            <circle cx="360" cy="264" r="18" fill="#dff6ef" />
            <circle cx="126" cy="316" r="16" fill="#d7e7ff" />
            <path d="M320 78 C350 100 365 130 372 160" fill="none" stroke="#b7cdf8" stroke-width="6" stroke-linecap="round" />
            <path d="M96 280 C122 248 149 232 180 226" fill="none" stroke="#d7d0ff" stroke-width="6" stroke-linecap="round" />
          </svg>
        </div>
        <div class="section-copy">
          <span class="section-kicker">AI 学习助手</span>
          <h2>学习过程中，随时有人帮助你</h2>
          <p>
            AI 学习助手可以解释难懂的知识点、根据你的水平调整讲解方式、生成练习和测验，并分析错误原因。
          </p>
          <div class="chat-stack">
            <div class="chat-bubble user">我不太理解这个知识点</div>
            <div class="chat-bubble ai">我换一种方式解释给你</div>
            <div class="chat-bubble ai soft">建议先复习前置知识，再开始练习</div>
          </div>
        </div>
      </section>

      <section id="about" class="landing-section landing-feedback" data-reveal>
        <div class="section-copy">
          <span class="section-kicker">持续反馈</span>
          <h2>学习不是一次诊断，而是持续进步</h2>
          <p>完成学习 → 提交测评 → 更新掌握度 → 获得新的学习建议。</p>
        </div>
        <div class="feedback-art">
          <div class="feedback-track">
            <span class="feedback-step done">完成学习</span>
            <span class="feedback-arrow">→</span>
            <span class="feedback-step current">提交测评</span>
            <span class="feedback-arrow">→</span>
            <span class="feedback-step waiting">更新掌握度</span>
            <span class="feedback-arrow">→</span>
            <span class="feedback-step done">新的建议</span>
          </div>
        </div>
      </section>

      <section class="landing-cta" data-reveal>
        <div>
          <span class="section-kicker">开始</span>
          <h2>准备好找到适合自己的学习方式了吗？</h2>
        </div>
        <RouterLink to="/diagnosis" class="button button-primary button-large">开始我的学习诊断 <ArrowRight :size="16" /></RouterLink>
      </section>

      <footer class="landing-footer">
        <div class="landing-brand landing-brand-footer">
          <span class="landing-mark">知</span>
          <span>
            <strong>知径</strong>
            <small>AI 个性化学习平台</small>
          </span>
        </div>
        <nav class="footer-links" aria-label="页脚链接">
          <a v-for="item in footerLinks" :key="item" href="#top">{{ item }}</a>
        </nav>
      </footer>
    </main>
  </div>
</template>
