<script setup lang="ts">
import { computed, ref } from "vue";
import { ArrowRight, ShieldCheck, Sparkles } from "lucide-vue-next";
import { RouterLink, useRouter } from "vue-router";
import BrandWordmark from "@/components/layout/BrandWordmark.vue";

const router = useRouter();
const email = ref("");
const password = ref("");

const canSubmit = computed(() => email.value.trim().length > 0 && password.value.trim().length > 0);

function handleSubmit() {
  void router.push("/app");
}
</script>

<template>
  <div class="auth-page">
    <header class="auth-page__top">
      <BrandWordmark compact />
      <RouterLink to="/register" class="auth-page__top-link">注册</RouterLink>
    </header>

    <main class="auth-page__shell">
      <section class="auth-page__copy">
        <span class="auth-page__eyebrow"><Sparkles :size="16" /> 登录后进入工作台</span>
        <h1>把课程知识、学习者画像和智能规划放在同一个平台里</h1>
        <p>进入你的课程知识库、图谱、诊断和规划工作区，继续处理当前的学习任务与证据流转。</p>
        <div class="auth-page__points">
          <span><ShieldCheck :size="15" /> 课程资料与证据可追溯</span>
          <span><ShieldCheck :size="15" /> 多智能体协同工作</span>
          <span><ShieldCheck :size="15" /> 规划与反馈持续更新</span>
        </div>
      </section>

      <section class="auth-card">
        <div class="auth-card__head">
          <strong>登录织知成径</strong>
          <p>使用你的工作账号继续。</p>
        </div>
        <form class="auth-form" @submit.prevent="handleSubmit">
          <label>
            <span>邮箱或账号</span>
            <input v-model="email" type="text" autocomplete="username" placeholder="name@school.edu" />
          </label>
          <label>
            <span>密码</span>
            <input v-model="password" type="password" autocomplete="current-password" placeholder="请输入密码" />
          </label>
          <button type="submit" class="auth-form__submit" :disabled="!canSubmit">
            进入工作台
            <ArrowRight :size="16" />
          </button>
        </form>
        <div class="auth-card__footer">
          <span>还没有账号？</span>
          <RouterLink to="/register">去注册</RouterLink>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  padding: 20px;
  color: #172b4d;
  background:
    radial-gradient(circle at top left, rgba(53, 106, 230, 0.08), transparent 28%),
    linear-gradient(180deg, #f8fbff 0%, #f6f8fc 100%);
}

.auth-page__top,
.auth-page__shell {
  width: min(1160px, calc(100% - 32px));
  margin: 0 auto;
}

.auth-page__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 6px 0 20px;
}

.auth-page__brand {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  color: inherit;
  text-decoration: none;
}

.auth-page__brand strong,
.auth-page__brand small {
  display: block;
}

.auth-page__brand strong {
  font-size: 17px;
}

.auth-page__brand small {
  color: #6a7d98;
  font-size: 12px;
}

.auth-page__top-link {
  padding: 10px 16px;
  color: #356ae6;
  text-decoration: none;
  border: 1px solid #d9e4f2;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.86);
}

.auth-page__shell {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(360px, 0.82fr);
  gap: 38px;
  align-items: center;
  min-height: calc(100vh - 100px);
  padding-bottom: 26px;
}

.auth-page__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #356ae6;
  font-size: 13px;
  font-weight: 800;
}

.auth-page h1 {
  max-width: 11ch;
  margin: 16px 0;
  font-size: clamp(42px, 4.6vw, 62px);
  line-height: 1.06;
  letter-spacing: 0;
}

.auth-page p {
  max-width: 580px;
  margin: 0;
  color: #5f718a;
  font-size: 17px;
  line-height: 1.8;
}

.auth-page__points {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
  margin-top: 24px;
  color: #5f718a;
  font-size: 13px;
}

.auth-page__points span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.auth-page__points svg {
  color: #1da35f;
}

.auth-card {
  padding: 26px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid #dfe8f3;
  border-radius: 24px;
  box-shadow: 0 24px 60px rgba(39, 72, 112, 0.12);
}

.auth-card__head strong {
  display: block;
  font-size: 22px;
}

.auth-card__head p {
  margin-top: 6px;
  color: #6a7d98;
  font-size: 14px;
}

.auth-form {
  display: grid;
  gap: 16px;
  margin-top: 22px;
}

.auth-form label {
  display: grid;
  gap: 8px;
}

.auth-form span {
  color: #51647c;
  font-size: 13px;
  font-weight: 700;
}

.auth-form input {
  min-height: 48px;
  padding: 0 14px;
  color: #172b4d;
  background: #fff;
  border: 1px solid #d9e4f2;
  border-radius: 12px;
  outline: none;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

.auth-form input:focus {
  border-color: #356ae6;
  box-shadow: 0 0 0 3px rgba(53, 106, 230, 0.14);
}

.auth-form__submit {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 48px;
  margin-top: 8px;
  color: #fff;
  background: #356ae6;
  border: 1px solid #356ae6;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 800;
  box-shadow: 0 12px 26px rgba(53, 106, 230, 0.18);
}

.auth-form__submit:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.auth-card__footer {
  display: flex;
  gap: 10px;
  margin-top: 18px;
  color: #6a7d98;
  font-size: 13px;
}

.auth-card__footer a {
  color: #356ae6;
  text-decoration: none;
  font-weight: 800;
}

@media (max-width: 920px) {
  .auth-page__shell {
    grid-template-columns: 1fr;
    gap: 24px;
    min-height: auto;
  }

  .auth-page h1 {
    max-width: 100%;
  }
}

@media (max-width: 620px) {
  .auth-page {
    padding: 14px;
  }

  .auth-page__top,
  .auth-page__shell {
    width: min(100%, 1160px);
  }

  .auth-page__top {
    padding-bottom: 16px;
  }

  .auth-card {
    padding: 20px;
  }
}
</style>
