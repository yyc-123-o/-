<script setup lang="ts">
import { Bell, Check, Palette, Settings2, UserRound } from "lucide-vue-next";
import { ref } from "vue";
const saved = ref(false);
</script>
<template>
  <div class="page-stack"><div class="page-intro"><div><span class="eyebrow">ACCOUNT</span><h2>个人中心</h2><p>管理学习档案和平台偏好。</p></div><Settings2 :size="22" class="icon-muted" /></div><section class="panel settings-panel"><div class="settings-row"><span class="settings-icon"><UserRound :size="18" /></span><div><strong>学习者身份</strong><p>张三 · 计算机科学与技术 · 本科</p></div><button class="button button-secondary">编辑</button></div><div class="settings-row"><span class="settings-icon"><Bell :size="18" /></span><div><strong>学习提醒</strong><p>每天 20:00 提醒完成今日任务</p></div><label class="switch"><input type="checkbox" checked /><span /></label></div><div class="settings-row"><span class="settings-icon"><Palette :size="18" /></span><div><strong>界面主题</strong><p>浅灰蓝教育科技主题</p></div><span class="status-pill">当前使用</span></div><div class="settings-actions"><button class="button button-primary" @click="saved = true">{{ saved ? "已保存" : "保存设置" }} <Check v-if="saved" :size="16" /></button></div></section></div>
</template>
