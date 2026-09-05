<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  ArrowRight,
  CheckCircle2,
  Download,
  RefreshCcw,
  Save,
  ShieldCheck,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";
import AbilityRadarChart from "@/components/AbilityRadarChart.vue";
import LearningTrendChart from "@/components/LearningTrendChart.vue";
import MasteryChart from "@/components/MasteryChart.vue";
import StateBlocks from "@/components/StateBlocks.vue";
import { useLearnerStore } from "@/stores/learner";
import { useLearningRecordsStore } from "@/stores/learningRecords";
import { formatMastery, getMasteryColor } from "@/utils/mastery";

const route = useRoute();
const router = useRouter();
const learner = useLearnerStore();
const records = useLearningRecordsStore();
const profileRange = computed(() => String(route.query.range || "30d"));
const profileLearnerId = ref(learner.selectedLearnerId || "");

const profile = computed(() => learner.profile);
const knowledgeMastery = computed(() => profile.value?.knowledge_mastery);
const points = computed(() =>
  Object.entries(knowledgeMastery.value?.points || {}).map(([id, point]) => ({ id, ...point })),
);
const masteryValue = computed(() => {
  const value = knowledgeMastery.value?.overall_mastery;
  return typeof value === "number" ? value : null;
});
const abilities = computed(() =>
  Object.entries(profile.value?.ability_level?.sub_dimensions || {})
    .map(([key, value]) => ({ key, ...value }))
    .filter((item) => typeof item.score === "number"),
);
const abilityDimensions = computed(() => {
  const source = Object.fromEntries(abilities.value.map((item) => [item.key, item.score]));
  const pick = (...keys: string[]) => {
    const key = keys.find((item) => typeof source[item] === "number");
    return key ? source[key] : null;
  };
  return [
    { key: "concept_understanding", label: "概念理解", score: pick("concept_understanding", "theoretical_understanding") },
    { key: "mathematical_foundation", label: "数学基础", score: pick("mathematical_foundation") },
    { key: "problem_solving", label: "问题解决", score: pick("problem_solving") },
    { key: "practical_application", label: "实践应用", score: pick("practical_application", "coding_ability") },
    { key: "knowledge_transfer", label: "知识迁移", score: pick("knowledge_transfer") },
    { key: "learning_stability", label: "学习稳定性", score: pick("learning_stability", "self_learning") },
  ];
});
const abilityValues = computed(() =>
  Object.fromEntries(abilityDimensions.value.map((item) => [item.key, item.score])),
);
const domainSummary = computed(() => knowledgeMastery.value?.domain_summary || {});
const domainValues = computed(() =>
  Object.fromEntries(
    Object.entries(domainSummary.value)
      .filter(([, value]) => typeof value.mean_mastery === "number")
      .map(([key, value]) => [key, value.mean_mastery as number]),
  ),
);
const snapshot = computed(() => learner.snapshot);
const snapshotMastery = computed(() =>
  (snapshot.value?.knowledge_mastery || [])
    .filter((item) => item.assessment_status === "assessed" && typeof item.mastery_score === "number"),
);
const snapshotAverage = computed(() => {
  const values = snapshotMastery.value.map((item) => item.mastery_score as number);
  return values.length ? values.reduce((total, value) => total + value, 0) / values.length : null;
});
const outcomeReport = computed(() => learner.outcomeReport);
const priorChapters = computed(() => profile.value?.prior_chapters || []);
const trendPoints = computed(() => {
  const history: Array<{ label: string; mastery: number | null; accuracy: number | null }> = priorChapters.value
    .filter((chapter) => typeof chapter.accuracy === "number")
    .map((chapter, index) => ({
      label: chapter.chapter_name || `阶段 ${index + 1}`,
      mastery: null,
      accuracy: chapter.accuracy as number,
    }));
  if (typeof knowledgeMastery.value?.overall_accuracy === "number") {
    history.push({
      label: "当前",
      mastery: masteryValue.value,
      accuracy: knowledgeMastery.value.overall_accuracy,
    });
  }
  return history;
});
const latestUpdate = computed(() =>
  profile.value?.meta?.diagnosed_at || snapshot.value?.generated_at || null,
);
const weeklyLearningHours = computed(() => {
  const hours = profile.value?.learner?.self_assessment?.weekly_hours;
  return typeof hours === "number" ? hours : null;
});
const confidenceScore = computed(() => {
  const value = profile.value?.knowledge_mastery?.overall_confidence;
  return typeof value === "number" ? value : null;
});
const stageLabel = computed(() => {
  const stage = profile.value?.ability_level?.overall?.toLowerCase();
  return stage === "beginner" ? "初阶" : stage === "intermediate" ? "进阶" : stage === "advanced" ? "高阶" : profile.value?.ability_level?.overall || "待评估";
});
const strongestAbilities = computed(() =>
  abilityDimensions.value.filter((item) => typeof item.score === "number").sort((a, b) => (b.score as number) - (a.score as number)).slice(0, 3),
);
const priorityAbilities = computed(() =>
  abilityDimensions.value.filter((item) => typeof item.score === "number").sort((a, b) => (a.score as number) - (b.score as number)).slice(0, 2),
);
const recentLearningMinutes = computed(() =>
  records.records
    .filter((record) => Date.now() - new Date(record.occurredAt).getTime() <= 7 * 86400000)
    .reduce((sum, record) => sum + Math.round((record.durationSeconds || 0) / 60), 0),
);
const measuredPointLabel = computed(() => {
  const tested = knowledgeMastery.value?.tested_kps;
  const total = knowledgeMastery.value?.total_kps;
  return typeof tested === "number" && typeof total === "number" ? `${tested}/${total}` : "待评估";
});
const strengths = computed(() =>
  [...points.value]
    .filter((point) => typeof point.mastery === "number")
    .sort((a, b) => (b.mastery as number) - (a.mastery as number))
    .slice(0, 3),
);
const focusAreas = computed(() =>
  [...points.value]
    .filter((point) => typeof point.mastery === "number")
    .sort((a, b) => (a.mastery as number) - (b.mastery as number))
    .slice(0, 3),
);
const recentChanges = computed(() =>
  (outcomeReport.value?.kp_changes || [])
    .filter((change) => change.before !== change.after)
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
    .slice(0, 8),
);
const preferences = computed(() => {
  const selfAssessment = profile.value?.learner?.self_assessment;
  return [
    { label: "学习目标", value: selfAssessment?.learning_goal || "尚未填写" },
    {
      label: "每周计划",
      value: selfAssessment?.weekly_hours ? `${selfAssessment.weekly_hours} 小时` : "尚未填写",
    },
    { label: "当前课程", value: profile.value?.learning_scope?.chapter_name || "尚未选择" },
    { label: "能力等级", value: profile.value?.ability_level?.overall || "待评估" },
  ];
});
const name = computed(() => profile.value?.learner?.name || learner.learnerName || "学习者");
const avatarText = computed(() => name.value.slice(0, 1));
const educationText = computed(() => {
  const education = profile.value?.learner?.education;
  return [education?.level, education?.major].filter(Boolean).join(" · ") || "学习者";
});
const profileSummary = computed(() =>
  profile.value?.diagnosis_summary?.short
  || "画像会根据诊断、学习记录和测评反馈持续更新，作为下一步学习规划的依据。",
);
const selectedPointId = computed(() => typeof route.query.kp === "string" ? route.query.kp : "");

function labelForAbility(key: string) {
  return abilityDimensions.value.find((item) => item.key === key)?.label || key.replaceAll("_", " ");
}

function formatDate(value: string | null) {
  if (!value) return "等待更新";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function updateRange(value: string) {
  void router.replace({ query: { ...route.query, range: value } });
}

function pointTitle(point: { id: string; name?: string }) {
  if (point.name) return point.name;
  const names: Record<string, string> = {
    scalar: "标量",
    vector: "向量",
    matrix: "矩阵",
    tensor: "张量",
    "matrix-operations": "矩阵运算",
    "matrix-multiplication": "矩阵乘法",
    convolution: "卷积运算",
    pooling: "池化",
    embedding: "嵌入表示",
    "gradient-descent": "梯度下降",
    relu: "ReLU",
    adam: "Adam",
  };
  const key = point.id.split(".").at(-1) || point.id;
  return names[key] || key.replaceAll("-", " ");
}

function evidenceLabel(level?: string) {
  const labels: Record<string, string> = {
    preliminary: "初步证据",
    limited: "证据有限",
    stable: "证据稳定",
    self_report: "逐点自评",
    none: "尚未测评",
  };
  return labels[level || "none"] || "尚未测评";
}

function deltaText(delta?: number) {
  if (typeof delta !== "number" || delta === 0) return "无变化";
  return `${delta > 0 ? "+" : ""}${Math.round(delta * 100)}%`;
}

function deltaClass(delta?: number) {
  if (typeof delta !== "number" || delta === 0) return "profile-delta-flat";
  return delta > 0 ? "profile-delta-up" : "profile-delta-down";
}

function verdictClass(verdict: string) {
  if (verdict.includes("显著") || verdict.includes("提升")) return "is-positive";
  if (verdict.includes("下降") || verdict.includes("退步")) return "is-negative";
  return "is-neutral";
}

async function refreshProfile() {
  await learner.loadLearners();
  if (!learner.profile && profileLearnerId.value) {
    await learner.selectLearner(profileLearnerId.value);
  }
}

async function loadExistingProfile() {
  if (!profileLearnerId.value) return;
  await learner.selectLearner(profileLearnerId.value);
}

function exportReport() {
  if (!profile.value) return;
  const blob = new Blob([JSON.stringify(profile.value, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `learner-profile-${profile.value.learner_id}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function openPoint(pointId: string) {
  void router.push({ path: "/learning-path", query: { kp: pointId } });
}

async function saveBaseline() {
  await learner.saveBaseline();
}

async function verifyOutcome() {
  await learner.verifyOutcome();
}

onMounted(async () => {
  if (learner.profile || learner.loading) return;
  await learner.loadLearners();
  if (learner.selectedLearnerId) {
    profileLearnerId.value = learner.selectedLearnerId;
  } else if (learner.learners.length === 1) {
    profileLearnerId.value = learner.learners[0].id;
    await loadExistingProfile();
  }
});
</script>

<template>
  <div class="profile-reference-page page-stack">
    <header class="profile-reference-header">
      <div>
        <p>基于学习记录、测评结果和路径进度持续更新。</p>
      </div>
      <div class="profile-header-actions">
        <select class="profile-range-select" :value="profileRange" aria-label="画像时间范围" @change="updateRange(($event.target as HTMLSelectElement).value)">
          <option value="30d">近30天</option>
          <option value="7d">近7天</option>
          <option value="90d">近90天</option>
          <option value="semester">本学期</option>
        </select>
        <button type="button" class="button button-secondary" :disabled="learner.loading" @click="refreshProfile">
          <RefreshCcw :size="16" /> 更新画像
        </button>
        <button type="button" class="profile-export-link" :disabled="!profile" @click="exportReport">
          <Download :size="15" /> 导出报告
        </button>
        <span class="profile-update-time">更新于 {{ formatDate(latestUpdate) }}</span>
      </div>
    </header>

    <p v-if="learner.error" class="profile-inline-error">
      画像数据暂时未同步，部分内容可能延迟显示。
      <button type="button" class="text-link" @click="refreshProfile">重新同步</button>
    </p>

    <section v-if="!profile && !snapshot" class="panel profile-empty-panel">
      <StateBlocks
        type="empty"
        title="还没有学习者画像"
        message="完成学情诊断后，这里会展示掌握度、能力结构和学习建议。"
      />
      <button type="button" class="button button-primary" @click="router.push('/diagnosis')">
        开始诊断 <ArrowRight :size="16" />
      </button>
      <div v-if="learner.learners.length" class="profile-empty-loader">
        <label for="profile-existing-learner">已有学习者画像</label>
        <div class="profile-empty-loader-row">
          <select id="profile-existing-learner" v-model="profileLearnerId">
            <option value="">请选择学习者</option>
            <option v-for="item in learner.learners" :key="item.id" :value="item.id">
              {{ item.name }} · {{ item.major }}
            </option>
          </select>
          <button
            type="button"
            class="button button-secondary"
            :disabled="!profileLearnerId || learner.loading"
            @click="loadExistingProfile"
          >
            {{ learner.loading ? "载入中…" : "载入画像" }}
          </button>
        </div>
        <small>载入已有诊断记录后，掌握度和能力结构会在此展示。</small>
      </div>
    </section>

    <template v-else>
      <section v-if="profile" class="profile-identity-card">
        <div class="profile-identity">
          <span class="profile-avatar">{{ avatarText }}</span>
          <div>
            <h3>{{ name }}</h3>
            <p>{{ educationText }}</p>
            <span class="profile-identity-meta">画像可信度 {{ confidenceScore === null ? "待评估" : formatMastery(confidenceScore) }}</span>
          </div>
        </div>
        <div class="profile-goal">
          <span>当前学习目标</span>
          <strong>{{ profile.learner.self_assessment?.learning_goal || "尚未填写学习目标" }}</strong>
          <small>{{ profile.learning_scope?.chapter_name || "尚未选择课程" }}</small>
        </div>
        <div class="profile-header-metric">
          <span>学习阶段</span>
          <strong>{{ stageLabel }}</strong>
        </div>
        <div class="profile-header-metric">
          <span>已测知识点</span>
          <strong>{{ measuredPointLabel }}</strong>
        </div>
        <div class="profile-header-metric">
          <span>平均掌握度</span>
          <strong>{{ masteryValue === null ? "待评估" : formatMastery(masteryValue) }}</strong>
        </div>
        <div class="profile-header-metric">
          <span>本周学习</span>
          <strong>{{ weeklyLearningHours === null ? `${recentLearningMinutes}分钟` : `${weeklyLearningHours}小时` }}</strong>
        </div>
        <button type="button" class="profile-goal-link" @click="router.push('/diagnosis/basic')">编辑学习目标</button>
      </section>

      <div class="profile-reference-grid">
        <main class="profile-reference-main">
          <div class="profile-chart-grid">
            <section class="panel profile-ability-card">
              <div class="profile-section-heading">
                <div>
                  <h3>六维能力画像</h3>
                </div>
                <select class="profile-view-select" aria-label="能力视图"><option>综合能力</option></select>
              </div>
              <div v-if="abilityDimensions.length === 6" class="profile-ability-layout">
                <AbilityRadarChart :values="abilityValues" />
                <div class="profile-ability-list">
                  <div v-for="ability in abilityDimensions" :key="ability.key">
                    <span><i />{{ ability.label }}</span>
                    <strong>{{ ability.score === null ? "待评估" : formatMastery(ability.score) }}</strong>
                  </div>
                </div>
              </div>
              <div v-else class="profile-chart-empty">当前能力证据不足，完成更多诊断后会显示能力结构。</div>
            </section>

            <section class="panel profile-domain-card">
              <div class="profile-section-heading">
                <div>
                <h3>知识领域掌握</h3>
                </div>
                <span class="profile-threshold">建议掌握线 75%</span>
              </div>
              <MasteryChart v-if="Object.keys(domainValues).length" :values="domainValues" />
              <div v-else class="profile-chart-empty">当前没有足够的领域掌握证据。</div>
            </section>
          </div>

          <section class="panel profile-rhythm-card">
            <div class="profile-section-heading">
              <div>
                <h3>学习节奏</h3>
              </div>
              <div class="profile-rhythm-metrics">
                <span>连续学习 <b>{{ records.records.length ? "—" : "暂无" }}</b></span>
                <span>高效时段 <b>{{ records.records.length ? "待分析" : "暂无" }}</b></span>
                <span>平均单次 <b>{{ records.records.length ? "待分析" : "暂无" }}</b></span>
              </div>
            </div>
            <div v-if="records.records.length" class="profile-rhythm-note">已记录 {{ records.records.length }} 条学习活动，更多节奏分析将在数据积累后展示。</div>
            <div v-else class="profile-chart-empty">学习记录不足，完成更多学习后可识别稳定节奏。</div>
          </section>

          <section class="panel profile-trend-card">
            <div class="profile-section-heading">
              <div>
                <h3>掌握度与测评趋势</h3>
                <p>基于已有阶段测评结果，不补造缺失的周期数据。</p>
              </div>
              <div class="profile-chart-legend">
                <span><i class="legend-line legend-line--blue" />平均掌握度</span>
                <span><i class="legend-line legend-line--teal" />测评正确率</span>
              </div>
            </div>
            <LearningTrendChart v-if="trendPoints.length >= 2" :points="trendPoints" />
            <div v-else class="profile-chart-empty profile-chart-empty--large">
              <TrendingUp :size="21" />
              <span>暂无足够的阶段数据，完成更多学习与测评后会形成趋势。</span>
            </div>
            <div class="profile-trend-summary">
              <div><span>当前已测均值</span><b>{{ formatMastery(snapshotAverage) }}</b></div>
              <div><span>学习稳定性</span><b>{{ priorChapters.length >= 2 ? "已有阶段记录" : "等待更多记录" }}</b></div>
              <div><span>最近连续记录</span><b>{{ profile?.meta?.total_interaction_count ?? "—" }} 次</b></div>
            </div>
          </section>

          <section class="panel profile-change-card">
            <div class="profile-section-heading">
              <div>
                <h3>近期知识变化</h3>
              </div>
              <button type="button" class="profile-table-link" @click="router.push('/assessment')">
                查看全部记录 <ArrowRight :size="14" />
              </button>
            </div>
            <div v-if="recentChanges.length" class="profile-change-table">
              <div class="profile-change-row profile-change-row--head">
                <span>知识点</span><span>上次掌握</span><span>当前掌握</span><span>变化</span><span>来源</span>
              </div>
              <button v-for="change in recentChanges" :key="change.kp_id" type="button" class="profile-change-row" @click="openPoint(change.kp_id)">
                <strong>{{ change.name }}</strong>
                <span>{{ formatMastery(change.before) }}</span>
                <span>{{ formatMastery(change.after) }}</span>
                <b :class="deltaClass(change.delta)">{{ deltaText(change.delta) }}</b>
                <small>{{ change.category || "测评更新" }}</small>
              </button>
            </div>
            <div v-else class="profile-chart-empty profile-chart-empty--table">完成一次学习和测评后，这里会记录知识点掌握度变化。</div>
          </section>

          <section v-if="profile" class="panel profile-points-card">
            <div class="profile-section-heading">
              <div>
                <h3>知识点掌握详情</h3>
              </div>
              <span class="profile-count-label">显示 {{ Math.min(points.length, 24) }} / {{ points.length }}</span>
            </div>
            <div class="profile-point-list">
              <button
                v-for="point in points.slice(0, 24)"
                :key="point.id"
                type="button"
                class="profile-point-row"
                :class="{ 'is-selected': point.id === selectedPointId }"
                @click="openPoint(point.id)"
              >
                <span class="profile-point-copy">
                  <strong>{{ pointTitle(point) }}</strong>
                  <small>
                    {{ point.domain }} ·
                    {{ point.test_count ? `测评 ${point.test_count} 题` : point.mastery === null ? "尚未测评" : "逐点自评" }}
                    · {{ evidenceLabel(point.evidence_level) }}
                  </small>
                </span>
                <span class="profile-point-bar">
                  <i :style="{ width: typeof point.mastery === 'number' ? `${point.mastery * 100}%` : '0%', backgroundColor: getMasteryColor(point.mastery) }" />
                </span>
                <b>{{ formatMastery(point.mastery) }}</b>
              </button>
            </div>
          </section>

          <section v-if="profile" class="panel profile-outcome-card">
            <div class="profile-section-heading">
              <div>
                <h3>学习成果检验</h3>
                <p>保存基线后继续学习，再比较前后画像。</p>
              </div>
              <RefreshCcw :size="19" class="profile-muted-icon" />
            </div>
            <div class="profile-outcome-toolbar">
              <button type="button" class="button button-secondary" :disabled="learner.loading" @click="saveBaseline">
                <Save :size="15" /> 保存基线画像
              </button>
              <button type="button" class="button button-primary" :disabled="learner.loading || !learner.baselineProfileId" @click="verifyOutcome">
                <RefreshCcw :size="15" /> 复诊并检验成果
              </button>
              <span v-if="learner.baselineProfileId" class="profile-baseline-state"><CheckCircle2 :size="14" /> 基线已保存</span>
              <span v-else class="profile-baseline-state is-pending">尚未保存基线</span>
            </div>
            <div v-if="outcomeReport" class="profile-outcome-result" :class="verdictClass(outcomeReport.overall_verdict)">
              <div>
                <span>本轮结果</span>
                <strong>{{ outcomeReport.overall_verdict }}</strong>
                <p>{{ outcomeReport.recommendation }}</p>
              </div>
              <TrendingUp v-if="verdictClass(outcomeReport.overall_verdict) === 'is-positive'" :size="23" />
              <TrendingDown v-else-if="verdictClass(outcomeReport.overall_verdict) === 'is-negative'" :size="23" />
              <ShieldCheck v-else :size="23" />
            </div>
            <p v-else class="profile-outcome-hint">完成一段学习并提交测评后，可以回来查看能力和知识点的真实变化。</p>
          </section>
        </main>

        <aside class="profile-reference-aside">
          <section class="panel profile-summary-card">
            <div class="profile-section-heading">
              <div>
                <h3>画像摘要</h3>
              </div>
              <ShieldCheck :size="18" class="profile-success-icon" />
            </div>
            <p class="profile-summary-copy">{{ profileSummary }}</p>
            <div class="profile-aside-section">
              <h4>学习优势</h4>
              <div v-if="strengths.length" class="profile-ranked-list">
                <button v-for="point in strengths" :key="point.id" type="button" @click="openPoint(point.id)">
                  <i /><span>{{ pointTitle(point) }}</span><b>{{ formatMastery(point.mastery) }}</b>
                </button>
              </div>
              <span v-else class="profile-aside-empty">暂无足够数据</span>
            </div>
            <div class="profile-aside-section">
              <h4>重点提升</h4>
              <div v-if="focusAreas.length" class="profile-ranked-list profile-ranked-list--focus">
                <button v-for="point in focusAreas" :key="point.id" type="button" @click="openPoint(point.id)">
                  <i /><span>{{ pointTitle(point) }}</span><b>{{ formatMastery(point.mastery) }}</b>
                </button>
              </div>
              <span v-else class="profile-aside-empty">暂无足够数据</span>
            </div>
          </section>

          <section class="panel profile-preference-card">
            <div class="profile-section-heading">
              <div>
                <h3>学习偏好</h3>
              </div>
              <Target :size="18" class="profile-muted-icon" />
            </div>
            <dl class="profile-preference-list">
              <div v-for="preference in preferences" :key="preference.label">
                <dt>{{ preference.label }}</dt>
                <dd>{{ preference.value }}</dd>
              </div>
            </dl>
          </section>

          <section class="profile-recommendation">
            <h3>当前建议</h3>
            <p>
              {{
                focusAreas.length
                  ? `优先复习${pointTitle(focusAreas[0])}，完成后再进入下一项课程任务。`
                  : "完成学情诊断后，系统会给出第一条个性化建议。"
              }}
            </p>
            <div class="profile-recommendation-actions">
              <button type="button" @click="router.push('/learning-path')">查看推荐路径</button>
              <button type="button" @click="router.push('/diagnosis/basic')">调整学习目标</button>
            </div>
          </section>
        </aside>
      </div>
    </template>
  </div>
</template>
