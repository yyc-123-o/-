<script setup lang="ts">
import { computed } from "vue";
import { BookOpen, ChevronRight, Network, Play } from "lucide-vue-next";
import { useRouter } from "vue-router";
import { courseKnowledgeBase } from "@/data/courseKnowledgeBase";
import { useLearnerStore } from "@/stores/learner";
import { useLearningPathStore } from "@/stores/learningPath";
import { adaptPathNodes, courseIdFromProfile } from "@/utils/knowledgeGraph";

const router = useRouter();
const learner = useLearnerStore();
const learningPath = useLearningPathStore();

const nodes = computed(() => courseKnowledgeBase.chapters.flatMap((chapter) => chapter.nodes));
const pathNodes = computed(() => adaptPathNodes(learningPath.nodes, {
  courseId: courseIdFromProfile(learner.profile),
  profile: learner.profile,
  snapshot: learner.snapshot,
  learningProgress: learningPath.run?.learning_progress,
}).nodes);
const progress = computed(() => {
  const completed = pathNodes.value.filter((node) => ["mastered", "completed"].includes(node.status)).length;
  return pathNodes.value.length ? Math.round((completed / pathNodes.value.length) * 100) : 0;
});
const chapterCount = computed(() => courseKnowledgeBase.chapters.length);
const knowledgeCount = computed(() => nodes.value.length);
const resourceCount = computed(() =>
  nodes.value.reduce((total, node) => total + node.lectures + node.examples + node.exercises + node.assessments, 0),
);

function openCourse() {
  void router.push(`/courses/${encodeURIComponent(courseKnowledgeBase.id)}/knowledge`);
}
</script>

<template>
  <div class="course-library page-stack">
    <header class="course-library-header">
      <div>
        <span class="eyebrow">课程中心 / 课程库</span>
        <h2>课程库</h2>
        <p>选择一门课程，按章节和知识点查看课程内容与关联资源。</p>
      </div>
      <button class="button button-primary" type="button" @click="openCourse">
        <Play :size="16" />
        进入当前课程
      </button>
    </header>

    <section class="course-library-grid">
      <article class="course-card course-card-featured">
        <div class="course-cover">
          <strong>卷积神经网络</strong>
          <span>CNN</span>
        </div>
        <div class="course-card-body">
          <div class="course-card-title">
            <div>
              <span class="eyebrow">当前课程</span>
              <h3>{{ courseKnowledgeBase.currentTrack }}</h3>
            </div>
            <BookOpen :size="22" />
          </div>
          <p>{{ courseKnowledgeBase.subtitle }}</p>
          <div class="course-metrics">
            <span><b>{{ chapterCount }}</b>章节</span>
            <span><b>{{ knowledgeCount }}</b>知识点</span>
            <span><b>{{ resourceCount }}</b>学习资源</span>
          </div>
          <div class="course-card-progress">
            <div><span>课程进度</span><b>{{ progress }}%</b></div>
            <div class="progress-track"><span :style="{ width: `${progress}%` }" /></div>
          </div>
          <div class="course-card-actions">
            <button class="button button-secondary" type="button" @click="openCourse">
              查看课程知识库
              <ChevronRight :size="16" />
            </button>
            <button class="icon-button" type="button" title="查看知识图谱" @click="router.push('/knowledge-graph')">
              <Network :size="18" />
            </button>
          </div>
        </div>
      </article>
    </section>

    <section class="course-library-note panel">
      <div>
        <strong>课程库与学习资源的边界</strong>
        <p>课程库负责课程、章节和知识点组织；跨课程搜索讲义、视频、示例、练习与测评，请进入“学习资源”。</p>
      </div>
      <button class="button button-secondary" type="button" @click="router.push('/resources')">
        浏览学习资源
        <ChevronRight :size="16" />
      </button>
    </section>
  </div>
</template>

<style scoped>
.course-library {
  color: #183153;
}

.course-library-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 6px 2px;
}

.course-library-header h2 {
  margin: 8px 0;
  color: #0f2f63;
  font-size: 30px;
}

.course-library-header p {
  margin: 0;
  color: #64748b;
}

.course-library-grid {
  display: grid;
  grid-template-columns: minmax(0, 760px);
  gap: 20px;
}

.course-card,
.course-library-note {
  border: 1px solid #e1eaf4;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
}

.course-card {
  display: grid;
  grid-template-columns: 190px minmax(0, 1fr);
  gap: 24px;
  padding: 24px;
}

.course-cover {
  display: grid;
  align-content: end;
  min-height: 190px;
  padding: 22px;
  border-radius: 16px;
  background: #123568;
  color: #fff;
}

.course-cover strong {
  font-size: 20px;
  line-height: 1.35;
}

.course-cover span {
  margin-top: 8px;
  color: #b9d5ff;
  font-size: 14px;
  letter-spacing: 0.12em;
}

.course-card-title,
.course-card-title > div,
.course-card-progress > div,
.course-card-actions {
  display: flex;
  align-items: center;
}

.course-card-title,
.course-card-progress > div {
  justify-content: space-between;
  gap: 14px;
}

.course-card-title svg {
  color: #2563eb;
}

.course-card-title h3 {
  margin: 6px 0 0;
  color: #0f2f63;
  font-size: 22px;
}

.course-card-body > p {
  margin: 14px 0 22px;
  color: #64748b;
}

.course-metrics {
  display: flex;
  gap: 0;
  margin-bottom: 24px;
  border-top: 1px solid #edf2f7;
  border-bottom: 1px solid #edf2f7;
}

.course-metrics span {
  display: grid;
  flex: 1;
  gap: 3px;
  padding: 12px 14px;
  border-left: 1px solid #edf2f7;
  color: #64748b;
  font-size: 12px;
}

.course-metrics span:first-child {
  border-left: 0;
}

.course-metrics b {
  color: #1d4ed8;
  font-size: 22px;
}

.course-card-progress > div {
  color: #64748b;
  font-size: 13px;
}

.course-card-progress b {
  color: #2563eb;
}

.course-card-progress .progress-track {
  height: 8px;
  margin-top: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: #e6eef8;
}

.course-card-progress .progress-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #2563eb;
}

.course-card-actions {
  justify-content: flex-end;
  gap: 10px;
  margin-top: 24px;
}

.course-library-note {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  max-width: 760px;
  padding: 18px 20px;
}

.course-library-note strong {
  color: #0f2f63;
}

.course-library-note p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.7;
}

@media (max-width: 720px) {
  .course-library-header,
  .course-library-note {
    align-items: flex-start;
    flex-direction: column;
  }

  .course-card {
    grid-template-columns: 1fr;
    padding: 16px;
  }

  .course-cover {
    min-height: 140px;
  }

  .course-metrics span {
    padding: 10px 8px;
  }
}
</style>
