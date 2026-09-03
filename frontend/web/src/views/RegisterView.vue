<script setup lang="ts">
import { computed, ref } from "vue";
import { ArrowRight, CheckCircle2, Sparkles } from "lucide-vue-next";
import { RouterLink, useRouter } from "vue-router";
import BrandWordmark from "@/components/layout/BrandWordmark.vue";

const router = useRouter();
const email = ref("");
const name = ref("");
const role = ref("课程建设者");
const password = ref("");

const canSubmit = computed(() => name.value.trim().length > 0 && email.value.trim().length > 0 && password.value.trim().length > 0);

function handleSubmit() {
  void router.push("/app");
}
</script>

<template>
  <div class="auth-page">
    <header class="auth-page__top">
      <BrandWordmark compact />
      <RouterLink to="/login" class="auth-page__top-link">登录</RouterLink>
    </header>

    <main class="auth-page__shell">
      <section class="auth-page__copy">
        <span class="auth-page__eyebrow"><Sparkles :size="16" /> 创建你的平台空间</span>
        <h1>把课程资料、知识图谱和学习反馈接到同一个工作流里</h1>
        <p>注册后即可进入我的学习，开始查看个性化课程路径、学习任务和反馈。</p>
        <div class="auth-page__points">
          <span><CheckCircle2 :size="15" /> 课程建设者、教师、学习者都能使用</span>
          <span><CheckCircle2 :size="15" /> 支持知识库与路径协同</span>
          <span><CheckCircle2 :size="15" /> 反馈会推动再次规划</span>
        </div>
      </section>

      <section class="auth-card">
        <div class="auth-card__head">
          <strong>注册织知成径</strong>
          <p>先创建一个演示账号，之后可以接入真实身份系统。</p>
        </div>
        <form class="auth-form" @submit.prevent="handleSubmit">
          <label>
            <span>你的姓名</span>
            <input v-model="name" type="text" autocomplete="name" placeholder="请输入姓名" />
          </label>
          <label>
            <span>工作邮箱</span>
            <input v-model="email" type="email" autocomplete="email" placeholder="name@school.edu" />
          </label>
          <label>
            <span>角色</span>
            <select v-model="role">
              <option>课程建设者</option>
              <option>教师与教学管理者</option>
              <option>学习者</option>
              <option>学校与教育机构</option>
            </select>
          </label>
          <label>
            <span>密码</span>
            <input v-model="password" type="password" autocomplete="new-password" placeholder="设置密码" />
          </label>
          <button type="submit" class="auth-form__submit" :disabled="!canSubmit">
            开始使用平台
            <ArrowRight :size="16" />
          </button>
        </form>
        <div class="auth-card__footer">
          <span>已经有账号？</span>
          <RouterLink to="/login">去登录</RouterLink>
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

.auth-form input,
.auth-form select {
  min-height: 48px;
  padding: 0 14px;
  color: #172b4d;
  background: #fff;
  border: 1px solid #d9e4f2;
  border-radius: 12px;
  outline: none;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

.auth-form input:focus,
.auth-form select:focus {
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
