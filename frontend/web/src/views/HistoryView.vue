<script setup lang="ts">
import { Clock3, FileCheck2, History as HistoryIcon, Route, Sparkles } from "lucide-vue-next";
const records = [
  { title: "完成章节诊断", detail: "识别 15 个待关注知识点", date: "今天", icon: Sparkles, tone: "purple" },
  { title: "生成个性化学习路径", detail: "围绕卷积神经网络安排学习内容", date: "昨天", icon: Route, tone: "blue" },
  { title: "完成知识点测评", detail: "掌握度从 42% 更新到 68%", date: "8 月 26 日", icon: FileCheck2, tone: "green" },
  { title: "浏览知识讲解", detail: "梯度下降与反向传播", date: "8 月 24 日", icon: Clock3, tone: "amber" },
];
</script>
<template>
  <div class="page-stack"><div class="page-intro"><div><span class="eyebrow">LEARNING HISTORY</span><h2>学习历史</h2><p>回看每一次学习、测评和掌握度变化，找到自己的进步轨迹。</p></div><HistoryIcon :size="22" class="icon-muted" /></div><div class="content-grid content-grid-main"><section class="panel"><div class="panel-heading"><div><span class="eyebrow">ACTIVITY</span><h2>最近学习任务</h2></div><span class="status-pill">持续更新</span></div><div class="timeline-list"><article v-for="record in records" :key="record.title" class="timeline-item"><span class="timeline-icon" :class="`tone-${record.tone}`"><component :is="record.icon" :size="16" /></span><div><strong>{{ record.title }}</strong><p>{{ record.detail }}</p></div><time>{{ record.date }}</time></article></div></section><section class="panel trend-panel"><div class="panel-heading"><div><span class="eyebrow">MASTERY TREND</span><h2>掌握度变化趋势</h2></div></div><div class="fake-chart"><span v-for="(height, index) in [32, 40, 37, 52, 58, 67, 72]" :key="index" :style="{ height: `${height}%` }" /><i /></div><div class="trend-caption"><span>诊断开始</span><b>+28%</b><span>当前</span></div></section></div><section class="panel"><div class="panel-heading"><div><span class="eyebrow">COMPLETED RESOURCES</span><h2>已完成资源</h2></div></div><div class="resource-history-grid"><div v-for="item in ['CNN 基础讲解', '梯度下降示例', '模型评估练习', '章节小测验']" :key="item" class="completed-resource"><span class="text-success">✓</span><div><strong>{{ item }}</strong><small>已完成 · 可随时复习</small></div></div></div></section></div>
</template>
