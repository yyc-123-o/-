<script setup lang="ts">
import { GraduationCap, Target, UserRound } from "lucide-vue-next";
import type { DiagnosisProfile } from "@/types/learner";
import StateBlocks from "./StateBlocks.vue";
defineProps<{ profile: DiagnosisProfile | null }>();
</script>
<template>
  <section class="panel profile-summary-card">
    <div class="panel-heading"><div><span class="eyebrow">PROFILE PREVIEW</span><h2>学习者画像预览</h2></div><span class="status-pill">实时更新</span></div>
    <div v-if="profile" class="profile-preview-grid">
      <div class="profile-avatar-large">{{ profile.learner.name.slice(0, 1) }}</div>
      <div class="profile-preview-main"><strong>{{ profile.learner.name }}</strong><span>{{ profile.learner.education?.major || "尚未填写专业" }}</span></div>
      <div class="profile-fact"><UserRound :size="16" /><span>学习阶段</span><b>{{ profile.learner.education?.level || "本科" }}</b></div>
      <div class="profile-fact"><GraduationCap :size="16" /><span>当前目标</span><b>{{ profile.learner.self_assessment?.learning_goal || "掌握核心课程" }}</b></div>
      <div class="profile-fact"><Target :size="16" /><span>画像状态</span><b class="text-success">已生成</b></div>
    </div>
    <StateBlocks v-else message="完成基础信息后，这里会同步展示你的学习档案。" />
  </section>
</template>
