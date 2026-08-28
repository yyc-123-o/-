<script setup lang="ts">
import { computed, watch } from "vue";
import { ArrowLeft, ArrowRight, BriefcaseBusiness, GraduationCap, Save, Target, UserRound } from "lucide-vue-next";
import { useRouter } from "vue-router";
import { useDiagnosisStore } from "@/stores/diagnosis";
import ProfileSummary from "@/components/ProfileSummary.vue";

const router = useRouter();
const diagnosis = useDiagnosisStore();
const fields = [
  { key: "name", label: "姓名", hint: "用什么名字称呼你？", icon: UserRound },
];
const knowledgeGroups = [
  { domain: "数学基础", items: ["高等数学", "线性代数", "概率论与数理统计"] },
  { domain: "机器学习基础", items: ["监督学习", "无监督学习", "模型评估"] },
  { domain: "深度学习", items: ["神经网络基础", "卷积神经网络 CNN", "Transformer"] },
  { domain: "优化算法", items: ["梯度下降", "反向传播", "Adam 优化器"] },
];
const levels = ["未学过", "了解", "基础", "熟练", "精通"];
watch(diagnosis.form, diagnosis.saveForm, { deep: true });
const completion = computed(() => {
  let score = 0;
  if (diagnosis.form.name) score += 25;
  if (diagnosis.form.education.major) score += 25;
  if (diagnosis.form.learning_goal) score += 25;
  if (diagnosis.form.weekly_hours) score += 25;
  return score;
});
async function save() {
  await diagnosis.submitBasic();
  router.push("/diagnosis/assessment");
}
</script>

<template>
  <div class="page-stack">
    <div class="page-intro"><div><span class="eyebrow">STEP 01 · FOUNDATION</span><h2>先告诉我们关于你的学习背景</h2><p>这些信息只用于调整诊断起点，不会替代后续的知识评估。</p></div><span class="save-status"><Save :size="15" /> 自动保存草稿</span></div>
    <div class="content-grid content-grid-main">
      <div class="page-stack">
        <section class="panel">
          <div class="panel-heading"><div><span class="eyebrow">YOUR BASICS</span><h2>个人信息</h2></div><span class="status-pill">{{ completion }}% 已完成</span></div>
          <div class="form-grid">
            <label v-for="field in fields" :key="field.key" class="form-field"><span class="form-label"><component :is="field.icon" :size="16" /><b>{{ field.label }}</b><small>{{ field.hint }}</small></span><input v-model="diagnosis.form.name" placeholder="例如：张三" /></label>
            <label class="form-field"><span class="form-label"><GraduationCap :size="16" /><b>学习阶段</b><small>帮助选择合适的起点</small></span><select v-model="diagnosis.form.education.level"><option>专科</option><option>本科</option><option>硕士</option><option>博士</option></select></label>
            <label class="form-field"><span class="form-label"><BriefcaseBusiness :size="16" /><b>专业方向</b><small>你正在学习的专业或方向</small></span><input v-model="diagnosis.form.education.major" placeholder="例如：计算机科学与技术" /></label>
            <label class="form-field"><span class="form-label"><GraduationCap :size="16" /><b>学校 / 机构</b><small>可选，用于完善档案</small></span><input v-model="diagnosis.form.education.institution" placeholder="例如：某大学" /></label>
            <label class="form-field"><span class="form-label"><Target :size="16" /><b>每周学习时间</b><small>用于估算路径节奏</small></span><input v-model.number="diagnosis.form.weekly_hours" type="number" min="1" max="40" /></label>
            <label class="form-field form-field-wide"><span class="form-label"><Target :size="16" /><b>当前学习目标</b><small>目标越具体，建议越贴合</small></span><textarea v-model="diagnosis.form.learning_goal" rows="3" placeholder="例如：掌握核心课程，能够独立完成一个图像分类项目" /></label>
          </div>
        </section>
        <section class="panel">
          <div class="panel-heading"><div><span class="eyebrow">STEP 02 · SELF ASSESSMENT</span><h2>快速标记你的知识掌握度</h2><p>不用追求准确，后续自适应测试会继续校准。</p></div></div>
          <div class="knowledge-groups">
            <div v-for="group in knowledgeGroups" :key="group.domain" class="knowledge-group-card">
              <div class="knowledge-group-heading"><div><h3>{{ group.domain }}</h3><span>{{ group.items.length }} 个核心知识点</span></div><span class="group-dot" /></div>
              <div v-for="item in group.items" :key="item" class="knowledge-card">
                <div><strong>{{ item }}</strong><small>选择你对这个知识点的直觉掌握程度</small></div>
                <div class="level-pills"><button v-for="level in levels" :key="level" type="button" :class="{ selected: level === '未学过' }">{{ level }}</button></div>
              </div>
            </div>
          </div>
        </section>
        <div v-if="diagnosis.error" class="inline-error">{{ diagnosis.error }}</div>
        <div class="page-actions"><button class="button button-quiet" @click="router.push('/diagnosis')"><ArrowLeft :size="17" /> 返回概览</button><button class="button button-primary button-large" :disabled="diagnosis.submitting" @click="save">{{ diagnosis.submitting ? "保存中…" : "保存并进入知识评估" }} <ArrowRight :size="17" /></button></div>
      </div>
      <div class="page-stack"><ProfileSummary :profile="diagnosis.form.name ? { profile_id: 'draft', learner_id: 'draft', profile_version: 'draft', learner: { name: diagnosis.form.name, education: diagnosis.form.education, self_assessment: { learning_goal: diagnosis.form.learning_goal } } } : null" /><section class="panel sticky-panel"><span class="eyebrow">WHY THIS MATTERS</span><h3>你的回答会影响什么？</h3><p>知径会用这些信息选择适合的起点、学习深度和练习形式。它们是学习画像的第一层，而不是最终结论。</p></section></div>
    </div>
  </div>
</template>
