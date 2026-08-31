<script setup lang="ts">
import { computed, watch } from "vue";
import { ArrowLeft, ArrowRight, BriefcaseBusiness, GraduationCap, Plus, Save, Target, Trash2, UserRound } from "lucide-vue-next";
import { useRouter } from "vue-router";
import { useDiagnosisStore } from "@/stores/diagnosis";
import ProfileSummary from "@/components/ProfileSummary.vue";
import type { DomainAssessment, ProjectExperience } from "@/types/diagnosis";

const router = useRouter();
const diagnosis = useDiagnosisStore();
const levels = [
  { label: "未学过", value: "未学过" },
  { label: "基本了解", value: "基本了解" },
  { label: "基础", value: "基础" },
  { label: "熟练", value: "熟练" },
  { label: "精通", value: "精通" },
] as const;
type KnowledgeItem = { name: string; kp_id: string };
type DomainConfig =
  | { domain: string; mode: "knowledge_points"; groups: Array<{ group: string; items: KnowledgeItem[] }> }
  | { domain: string; mode: "guided_questions"; questions: Array<{ id: string; prompt: string; placeholder: string }> };

const domainConfigs: DomainConfig[] = [
  { domain: "数学基础", mode: "knowledge_points", groups: [
    { group: "高等数学（微积分）", items: [{ name: "偏导数与梯度", kp_id: "kp_005" }, { name: "链式法则与雅可比矩阵", kp_id: "kp_005" }] },
    { group: "线性代数", items: [{ name: "矩阵乘法与转置", kp_id: "kp_004" }, { name: "逆矩阵与秩", kp_id: "kp_004" }, { name: "特征值与特征分解", kp_id: "kp_004" }, { name: "SVD 奇异值分解", kp_id: "kp_004" }] },
    { group: "概率论与数理统计", items: [{ name: "条件概率与贝叶斯定理", kp_id: "kp_003" }, { name: "常见概率分布", kp_id: "kp_003" }, { name: "期望、方差与协方差", kp_id: "kp_003" }, { name: "最大似然估计 MLE", kp_id: "kp_003" }, { name: "信息论基础（熵、交叉熵、KL 散度）", kp_id: "kp_026" }] },
  ] },
  { domain: "机器学习基础", mode: "guided_questions", questions: [
    { id: "q_ml_methods", prompt: "1. 快速列举你知道的机器学习算法，并标注类别（建议 5-8 个）。", placeholder: "例如：监督学习：线性回归、SVM、随机森林；无监督学习：K-Means、PCA" },
    { id: "q_ml_model_compare", prompt: "2. 从线性回归与逻辑回归、L1 与 L2、Bagging 与 Boosting、决策树与随机森林中任选两组，写出核心区别。", placeholder: "用 1-2 句话描述每组区别即可。" },
    { id: "q_ml_practice", prompt: "3. 简述一个你做过的机器学习项目或练习：使用的模型、解决的问题和大致结果。", placeholder: "没有做过也可以写计划中的项目。" },
    { id: "q_ml_metrics", prompt: "4. 从癌症筛查、垃圾邮件过滤、商品推荐、不平衡二分类中任选两个，写出你会使用的评估指标。", placeholder: "例如：癌症筛查 → 召回率。" },
  ] },
  { domain: "深度学习", mode: "knowledge_points", groups: [
    { group: "深度学习基础（BP / MLP）", items: [{ name: "感知机与多层感知机（MLP）", kp_id: "kp_011" }, { name: "前向传播计算过程", kp_id: "kp_011" }, { name: "激活函数（ReLU、Sigmoid、Tanh、GELU）", kp_id: "kp_015" }, { name: "反向传播与链式求导", kp_id: "kp_017" }] },
    { group: "卷积神经网络 CNN", items: [{ name: "卷积运算（互相关与卷积）", kp_id: "kp_012" }, { name: "卷积核、步长、填充与感受野", kp_id: "kp_012" }, { name: "池化层（Max / Avg Pooling）", kp_id: "kp_012" }, { name: "经典架构（LeNet、AlexNet、VGG、ResNet）", kp_id: "kp_012" }, { name: "1×1 卷积的作用", kp_id: "kp_012" }] },
    { group: "循环网络与注意力机制", items: [{ name: "RNN 序列建模原理", kp_id: "kp_013" }, { name: "LSTM / GRU 门控结构", kp_id: "kp_013" }, { name: "自注意力与多头注意力", kp_id: "kp_014" }, { name: "Transformer 整体结构", kp_id: "kp_014" }] },
  ] },
  { domain: "优化算法", mode: "knowledge_points", groups: [
    { group: "梯度下降变体", items: [{ name: "批量梯度下降 BGD", kp_id: "kp_016" }, { name: "随机梯度下降 SGD", kp_id: "kp_016" }, { name: "Mini-batch SGD", kp_id: "kp_016" }, { name: "带动量的 SGD", kp_id: "kp_016" }] },
    { group: "自适应优化器", items: [{ name: "AdaGrad / RMSProp 原理", kp_id: "kp_018" }, { name: "Adam 优化器", kp_id: "kp_018" }, { name: "AdamW（解耦权重衰减）", kp_id: "kp_018" }] },
    { group: "正则化与学习率", items: [{ name: "L1 / L2 权重衰减", kp_id: "kp_019" }, { name: "Dropout 随机失活", kp_id: "kp_019" }, { name: "Early Stopping 早停", kp_id: "kp_019" }, { name: "Warmup 与学习率调度", kp_id: "kp_020" }] },
  ] },
  { domain: "实践应用", mode: "guided_questions", questions: [
    { id: "q_py_stack", prompt: "1. 列出你最熟练的 3-5 个工具或框架，并标注熟练度（熟练、会用、用过）。", placeholder: "例如：Python（熟练）、NumPy（熟练）、PyTorch（会用）。" },
    { id: "q_data_pipeline", prompt: "2. 数据预处理时你最常用的三个操作是什么？各说明适用场景。", placeholder: "例如：标准化用于数值特征，OneHot 用于类别特征。" },
    { id: "q_tuning_deploy", prompt: "3. 你常用什么方法调节超参数？是否部署过模型？请写出一种导出格式。", placeholder: "例如：使用网格搜索，导出 ONNX；没有经验也可以如实填写。" },
    { id: "q_debug_story", prompt: "4. 列举训练模型时遇到的 1-2 个问题，并写出解决思路。", placeholder: "例如：Loss 不下降时检查数据归一化、梯度和学习率。" },
  ] },
];

function initializeDomainAssessments() {
  for (const config of domainConfigs) {
    let assessment = diagnosis.domains.find((item) => item.domain === config.domain);
    if (!assessment) {
      assessment = { domain: config.domain, mode: config.mode, courses: [], note: "", guided_answers: {} };
      diagnosis.domains.push(assessment);
    }
    assessment.mode = config.mode;
    assessment.guided_answers ||= {};
    if (config.mode === "knowledge_points") {
      for (const group of config.groups) for (const item of group.items) {
        if (!assessment.courses.some((course) => course.name === item.name)) assessment.courses.push({ name: item.name, level: "未学过", kp_id: item.kp_id });
      }
    } else if (!assessment.courses.some((course) => course._synthetic)) {
      assessment.courses.push({ name: `${config.domain}（整体自评）`, level: "基本了解", _synthetic: true });
    }
  }
}

// The template needs these records on its very first render.
initializeDomainAssessments();
watch([diagnosis.form, diagnosis.domains, diagnosis.projects], diagnosis.saveForm, { deep: true });
function assessmentFor(domain: string): DomainAssessment { return diagnosis.domains.find((item) => item.domain === domain)!; }
function courseFor(domain: string, name: string) { return assessmentFor(domain).courses.find((course) => course.name === name)!; }
function guidedAnswer(domain: string, id: string) { return assessmentFor(domain).guided_answers?.[id] || ""; }
function setGuidedAnswer(domain: string, id: string, value: string) { const assessment = assessmentFor(domain); assessment.guided_answers ||= {}; assessment.guided_answers[id] = value; }
function addProject() { diagnosis.projects.push({ name: "", role: "", description: "", tech_stack: [], duration_months: 0 }); }
function removeProject(project: ProjectExperience) { const index = diagnosis.projects.indexOf(project); if (index >= 0) diagnosis.projects.splice(index, 1); }
const completion = computed(() => {
  let score = 0;
  if (diagnosis.form.name) score += 20;
  if (diagnosis.form.education.major) score += 20;
  if (diagnosis.form.learning_goal) score += 20;
  if (diagnosis.form.weekly_hours) score += 20;
  if (diagnosis.form.education.gpa !== null) score += 20;
  return score;
});
async function save() { await diagnosis.submitBasic(); router.push("/diagnosis/assessment"); }
</script>

<template>
  <div class="page-stack">
    <div class="page-intro"><div><span class="eyebrow">STEP 01 · LEARNING PROFILE</span><h2>建立你的学习画像</h2><p>这是自评问卷，不是测试题。请按真实经历填写，后续诊断会继续校准。</p></div><span class="save-status"><Save :size="15" /> 自动保存草稿</span></div>
    <div class="content-grid content-grid-main">
      <div class="page-stack">
        <section class="panel">
          <div class="panel-heading"><div><span class="eyebrow">YOUR BASICS</span><h2>个人信息</h2></div><span class="status-pill">{{ completion }}% 已完成</span></div>
          <div class="form-grid">
            <label class="form-field"><span class="form-label"><UserRound :size="16" /><b>姓名</b><small>用什么名字称呼你？</small></span><input v-model="diagnosis.form.name" placeholder="例如：张三" /></label>
            <label class="form-field"><span class="form-label"><GraduationCap :size="16" /><b>学历</b><small>帮助选择合适的起点</small></span><select v-model="diagnosis.form.education.level"><option>专科</option><option>本科</option><option>硕士</option><option>博士</option></select></label>
            <label class="form-field"><span class="form-label"><BriefcaseBusiness :size="16" /><b>专业方向</b><small>你正在学习的专业或方向</small></span><input v-model="diagnosis.form.education.major" placeholder="例如：计算机科学与技术" /></label>
            <label class="form-field"><span class="form-label"><GraduationCap :size="16" /><b>学校 / 机构</b><small>可选，用于完善档案</small></span><input v-model="diagnosis.form.education.institution" placeholder="例如：某大学" /></label>
            <label class="form-field"><span class="form-label"><Target :size="16" /><b>GPA</b><small>可选，用于了解学习背景</small></span><input v-model.number="diagnosis.form.education.gpa" type="number" min="0" max="4" step="0.1" placeholder="例如：3.2" /></label>
            <label class="form-field"><span class="form-label"><Target :size="16" /><b>每周学习时间（小时）</b><small>用于估算路径节奏</small></span><input v-model.number="diagnosis.form.weekly_hours" type="number" min="1" max="40" /></label>
            <label class="form-field form-field-wide"><span class="form-label"><Target :size="16" /><b>当前学习目标</b><small>目标越具体，建议越贴合</small></span><textarea v-model="diagnosis.form.learning_goal" rows="3" placeholder="例如：掌握核心课程，能够独立完成一个图像分类项目" /></label>
          </div>
        </section>

        <section v-for="config in domainConfigs" :key="config.domain" class="panel">
          <div class="panel-heading"><div><span class="eyebrow">SELF ASSESSMENT</span><h2>{{ config.domain }}</h2><p>{{ config.mode === 'knowledge_points' ? '逐项选择你对知识点的掌握程度。' : '通过开放回答了解你的实践经验。' }}</p></div><span class="status-pill">{{ config.mode === 'knowledge_points' ? '知识点自评' : '引导问答' }}</span></div>
          <template v-if="config.mode === 'knowledge_points'">
            <div v-for="group in config.groups" :key="group.group" class="knowledge-group-card">
              <div class="knowledge-group-heading"><div><h3>{{ group.group }}</h3><span>{{ group.items.length }} 个知识点</span></div><span class="group-dot" /></div>
              <div v-for="item in group.items" :key="item.name" class="knowledge-card"><div><strong>{{ item.name }}</strong><small>选择你的直觉掌握程度</small></div><div class="level-pills"><button v-for="level in levels" :key="level.value" type="button" :aria-pressed="courseFor(config.domain, item.name).level === level.value" :class="{ selected: courseFor(config.domain, item.name).level === level.value }" @click="courseFor(config.domain, item.name).level = level.value">{{ level.label }}</button></div></div>
            </div>
          </template>
          <template v-else>
            <label class="form-field guided-overall"><span class="form-label"><Target :size="16" /><b>该领域整体自评</b><small>请选择最接近当前状态的等级</small></span><select v-model="assessmentFor(config.domain).courses.find((course) => course._synthetic)!.level"><option v-for="level in levels" :key="level.value" :value="level.value">{{ level.label }}</option></select></label>
            <label v-for="question in config.questions" :key="question.id" class="form-field guided-question"><span class="form-label"><b>{{ question.prompt }}</b></span><textarea :value="guidedAnswer(config.domain, question.id)" :placeholder="question.placeholder" rows="3" @input="setGuidedAnswer(config.domain, question.id, ($event.target as HTMLTextAreaElement).value)" /></label>
          </template>
          <label class="form-field"><span class="form-label"><b>补充说明</b><small>可填写课程经历、学习困难或其他背景</small></span><textarea v-model="assessmentFor(config.domain).note" rows="2" placeholder="选填" /></label>
        </section>

        <section class="panel"><div class="panel-heading"><div><span class="eyebrow">PROJECT EXPERIENCE</span><h2>项目经历</h2><p>选填，用于了解你的实际应用背景。</p></div><button type="button" class="button button-quiet" @click="addProject"><Plus :size="16" /> 添加项目</button></div><div v-if="!diagnosis.projects.length" class="empty-state">暂未添加项目经历</div><div v-for="(project, projectIndex) in diagnosis.projects" :key="projectIndex" class="project-editor"><div class="form-grid"><label class="form-field"><span class="form-label"><b>项目名称</b></span><input v-model="project.name" placeholder="例如：图像分类项目" /></label><label class="form-field"><span class="form-label"><b>担任角色</b></span><input v-model="project.role" placeholder="例如：模型开发" /></label><label class="form-field form-field-wide"><span class="form-label"><b>项目描述</b></span><textarea v-model="project.description" rows="3" placeholder="你负责了什么，项目解决了什么问题？" /></label></div><button type="button" class="button button-quiet project-remove" title="删除项目" @click="removeProject(project)"><Trash2 :size="16" /> 删除</button></div></section>
        <div v-if="diagnosis.error" class="inline-error">{{ diagnosis.error }}</div>
        <div class="page-actions"><button class="button button-quiet" @click="router.push('/diagnosis')"><ArrowLeft :size="17" /> 返回概览</button><button class="button button-primary button-large" :disabled="diagnosis.submitting" @click="save">{{ diagnosis.submitting ? "保存中…" : "保存并进入知识评估" }} <ArrowRight :size="17" /></button></div>
      </div>
      <div class="page-stack"><ProfileSummary :profile="diagnosis.form.name ? { profile_id: 'draft', learner_id: 'draft', profile_version: 'draft', learner: { name: diagnosis.form.name, education: diagnosis.form.education, self_assessment: { learning_goal: diagnosis.form.learning_goal } } } : null" /><section class="panel sticky-panel"><span class="eyebrow">WHY THIS MATTERS</span><h3>你的回答会影响什么？</h3><p>知径会用这些信息选择适合的起点、学习深度和练习形式。它们是学习画像的第一层，而不是最终结论。</p></section></div>
    </div>
  </div>
</template>

<style scoped>
.guided-overall { max-width: 320px; margin-bottom: 18px; }
.guided-question textarea { min-height: 96px; }
.project-editor { position: relative; padding: 18px; margin-top: 12px; border: 1px solid var(--line, #e5e7eb); border-radius: 8px; background: var(--surface-subtle, #fafafa); }
.project-remove { margin-top: 8px; color: var(--danger, #dc2626); }
.empty-state { padding: 20px; color: var(--muted, #64748b); text-align: center; border: 1px dashed var(--line, #dbe2ea); border-radius: 8px; }
</style>
