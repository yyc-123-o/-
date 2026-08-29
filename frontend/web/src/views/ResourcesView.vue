<script setup lang="ts">
import { computed, ref } from "vue";
import MarkdownIt from "markdown-it";
import markdownItKatex from "markdown-it-katex";
import "katex/dist/katex.min.css";
import { BookOpen, CheckCircle2, Code2, Dumbbell, FileCheck2, MessageCircle, Sparkles } from "lucide-vue-next";
import { useRouter } from "vue-router";
import ResourceCard from "@/components/ResourceCard.vue";
import AICoachPanel from "@/components/AICoachPanel.vue";
import StateBlocks from "@/components/StateBlocks.vue";
import { useLearningPathStore } from "@/stores/learningPath";

const router = useRouter();
const path = useLearningPathStore();
const active = ref("lecture");
const md = new MarkdownIt({ html: false, breaks: true }).use(markdownItKatex);
const resources = computed(() => path.run?.resources as Record<string, any> | null);
const content = computed(() => {
  const item = resources.value?.[active.value] || resources.value?.[`${active.value}_resource`];
  return item?.markdown || item?.content || `## ${active.value === "lecture" ? "知识讲解" : "学习材料"}\n\n当前节点还没有返回完整内容。请继续使用诊断和课程规划流程。`;
});
const resourceCards = [
  { key: "lecture", title: "知识讲解", description: "从直觉、公式到关键概念，分步建立理解。", kind: "讲解" },
  { key: "example", title: "示例演示", description: "用一个完整例子把知识点放进真实问题。", kind: "示例" },
  { key: "practice", title: "实践练习", description: "动手完成一个小任务，巩固迁移能力。", kind: "练习" },
  { key: "quiz", title: "小测验", description: "用几道题检查是否真的掌握。", kind: "测验" },
];
function ask(value: string) { window.localStorage.setItem("zhijing.last-question", value); }
</script>

<template>
  <div class="page-stack">
    <div class="page-intro"><div><span class="eyebrow">LEARNING RESOURCES</span><h2>把知识学进去，而不是只看完</h2><p>当前资源围绕推荐知识点组织，支持讲解、示例、练习和测验的连续学习。</p></div><span class="status-pill status-pill-purple"><Sparkles :size="14" /> AI 辅助学习</span></div>
    <section v-if="!path.run" class="panel"><StateBlocks type="empty" title="还没有当前学习资源" message="生成学习路径后，系统会为当前推荐节点准备资源。" /><button class="button button-primary" @click="router.push('/learning-path')">查看学习路径</button></section>
    <template v-else>
      <section class="resource-context"><div class="resource-context-icon"><Code2 :size="22" /></div><div><span class="eyebrow">CURRENT NODE</span><h2>{{ path.currentNode?.title || path.currentNode?.name || "当前推荐知识点" }}</h2><p>{{ path.currentNode?.summary || "围绕当前推荐节点完成一次讲解、练习和测评。" }}</p></div><span class="status-pill">{{ path.run.status === "completed" ? "正式资源" : "candidate preview" }}</span></section>
      <div class="resource-card-grid"><ResourceCard v-for="item in resourceCards" :key="item.key" :title="item.title" :description="item.description" :kind="item.kind" :status="path.run?.resources ? '正式资源' : 'candidate preview'" @open="active = item.key" /></div>
      <div class="content-grid content-grid-main"><section class="panel learning-reader"><div class="reader-tabs"><button v-for="item in resourceCards" :key="item.key" :class="{ active: active === item.key }" @click="active = item.key">{{ item.title }}</button></div><article class="markdown-content" v-html="md.render(content)" /><div class="reader-actions"><button class="button button-secondary" @click="router.push('/assessment')"><FileCheck2 :size="16" /> 去完成测评</button><button class="button button-primary" @click="path.completeNode"><CheckCircle2 :size="16" /> 标记已完成</button></div></section><aside class="page-stack"><AICoachPanel @send="ask" /><section class="panel source-panel"><div class="panel-heading"><div><span class="eyebrow">EVIDENCE MANIFEST</span><h3>知识来源</h3></div><BookOpen :size="18" class="icon-muted" /></div><p>资源生成会区分正式依据和 candidate preview，当前结果以服务端返回的状态为准。</p><div class="source-status"><span class="online-dot" /> 已连接知识检索服务</div></section></aside></div>
    </template>
  </div>
</template>
