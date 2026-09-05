<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, BookOpen, CheckCircle2, Clock3 } from "lucide-vue-next";
import { findResourceById } from "@/utils/resourceCatalog";

const route = useRoute();
const router = useRouter();
const resource = computed(() => findResourceById(String(route.params.resourceId || "")));
const mode = computed(() => String(route.query.mode || "learn"));
</script>

<template>
  <div class="resource-learning page-stack">
    <button class="button button-secondary back-button" type="button" @click="router.back()">
      <ArrowLeft :size="16" />
      返回
    </button>

    <section v-if="resource" class="panel resource-reader">
      <div class="reader-heading">
        <span class="reader-icon"><component :is="resource.icon" :size="24" /></span>
        <div>
          <span class="eyebrow">{{ mode === "review" ? "复习资源" : "学习资源" }}</span>
          <h2>{{ resource.title }}</h2>
          <p>{{ resource.courseTitle }} · {{ resource.chapterTitle }} · {{ resource.knowledgePointTitle }}</p>
        </div>
      </div>

      <div class="reader-meta">
        <span><BookOpen :size="16" /> {{ resource.typeLabel }}</span>
        <span><Clock3 :size="16" /> {{ resource.questionCount ? `${resource.questionCount} 题` : `${resource.duration} 分钟` }}</span>
        <span><CheckCircle2 :size="16" /> {{ resource.status === "completed" ? "已完成" : "未完成" }}</span>
      </div>

      <article class="reader-body">
        <h3>资源内容</h3>
        <p>当前项目尚未接通独立资源正文接口，因此这里先展示来自课程知识库的资源上下文。接通接口后，`/learn/{{ resource.id }}` 会加载对应资源正文、练习或测评。</p>
      </article>
    </section>

    <section v-else class="panel resource-reader empty-reader">
      <h2>没有找到对应资源</h2>
      <p>该资源可能尚未生成，或链接中的 resourceId 已失效。</p>
      <RouterLink class="button button-primary" to="/resources">返回学习资源</RouterLink>
    </section>
  </div>
</template>

<style scoped>
.back-button {
  width: fit-content;
}

.resource-reader {
  padding: 28px;
  border-radius: 16px;
}

.reader-heading {
  display: flex;
  gap: 16px;
  align-items: center;
}

.reader-icon {
  display: grid;
  place-items: center;
  width: 58px;
  height: 58px;
  color: #2563eb;
  background: #eef6ff;
  border-radius: 16px;
}

.reader-heading h2 {
  margin: 6px 0;
  color: #0f2f63;
}

.reader-heading p,
.reader-body p,
.empty-reader p {
  margin: 0;
  color: #64748b;
  line-height: 1.8;
}

.reader-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: 24px 0;
  padding: 14px;
  border: 1px solid #e4edf7;
  border-radius: 14px;
  background: #fbfdff;
}

.reader-meta span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #38516f;
  font-weight: 700;
}

.reader-body {
  min-height: 260px;
  padding: 22px;
  border: 1px solid #e4edf7;
  border-radius: 14px;
  background: #fff;
}

.reader-body h3 {
  margin-top: 0;
  color: #0f2f63;
}

.empty-reader {
  display: grid;
  justify-items: start;
  gap: 12px;
}
</style>
