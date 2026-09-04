<script setup lang="ts">
import { Bell, Check, Palette, Settings2, UserRound } from "lucide-vue-next";
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { settingsApi, type LearnerTheme } from "@/api/settings";
import { useLearnerStore } from "@/stores/learner";

const router = useRouter();
const learner = useLearnerStore();
const saved = ref(false);
const loading = ref(false);
const error = ref("");
const remindersEnabled = ref(true);
const theme = ref<LearnerTheme>("light");
const learnerId = computed(() => learner.profile?.learner_id || learner.selectedLearnerId || "anonymous");
const learnerName = computed(() => learner.profile?.learner?.name || "尚未选择学习者");
const learnerEducation = computed(() => {
  const education = learner.profile?.learner?.education;
  return [education?.major, education?.level].filter(Boolean).join(" · ") || "请先完成基础信息";
});

async function loadPreferences() {
  loading.value = true;
  error.value = "";
  try {
    const preferences = await settingsApi.get(learnerId.value);
    remindersEnabled.value = preferences.reminders_enabled;
    theme.value = preferences.theme;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "设置加载失败";
  } finally {
    loading.value = false;
  }
}

async function save() {
  loading.value = true;
  saved.value = false;
  error.value = "";
  try {
    const preferences = await settingsApi.update(learnerId.value, {
      reminders_enabled: remindersEnabled.value,
      theme: theme.value,
    });
    remindersEnabled.value = preferences.reminders_enabled;
    theme.value = preferences.theme;
    saved.value = true;
    window.setTimeout(() => { saved.value = false; }, 1800);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "设置保存失败";
  } finally {
    loading.value = false;
  }
}

function editLearner() {
  void router.push("/diagnosis/basic");
}

onMounted(async () => {
  if (!learner.profile && !learner.loading) await learner.loadLearners();
  await loadPreferences();
});

watch(learnerId, (next, previous) => {
  if (next !== previous) void loadPreferences();
});
</script>

<template>
  <div class="page-stack">
    <div class="page-intro"><div><span class="eyebrow">ACCOUNT</span><h2>个人中心</h2><p>管理学习档案和平台偏好。</p></div><Settings2 :size="22" class="icon-muted" /></div>
    <p v-if="error" class="inline-error">{{ error }}</p>
    <section class="panel settings-panel">
      <div class="settings-row"><span class="settings-icon"><UserRound :size="18" /></span><div><strong>学习者身份</strong><p>{{ learnerName }} · {{ learnerEducation }}</p></div><button class="button button-secondary" type="button" @click="editLearner">编辑</button></div>
      <div class="settings-row"><span class="settings-icon"><Bell :size="18" /></span><div><strong>学习提醒</strong><p>{{ remindersEnabled ? "每天 20:00 提醒完成今日任务" : "已关闭学习提醒" }}</p></div><label class="switch"><input v-model="remindersEnabled" type="checkbox" :disabled="loading" /><span /></label></div>
      <div class="settings-row"><span class="settings-icon"><Palette :size="18" /></span><div><strong>界面主题</strong><p>选择下次进入平台时使用的界面主题。</p></div><select v-model="theme" :disabled="loading" aria-label="界面主题"><option value="light">浅色主题</option><option value="dark">深色主题</option><option value="system">跟随系统</option></select></div>
      <div class="settings-actions"><button class="button button-primary" type="button" :disabled="loading" @click="save">{{ loading ? "保存中…" : saved ? "已保存" : "保存设置" }} <Check v-if="saved" :size="16" /></button></div>
    </section>
  </div>
</template>
