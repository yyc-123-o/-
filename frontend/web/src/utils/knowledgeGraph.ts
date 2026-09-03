import type { DiagnosisProfile, LearnerSnapshot } from "@/types/learner";
import type { LearningProgress, PathNode } from "@/types/planning";
import type {
  KnowledgeDifficulty,
  KnowledgeEdge,
  KnowledgeNode,
  KnowledgeStatus,
  LearningPathSummary,
} from "@/types/knowledgeGraph";
import { clampMastery } from "./mastery";

const MASTERY_THRESHOLD = 0.75;
const UNLOCK_THRESHOLD = 0.6;
const DEFAULT_UNLOCK_POLICY = "completion_based";

const TITLE_MAP: Record<string, string> = {
  "math.linear-algebra.scalar": "标量基础",
  "math.linear-algebra.vector": "向量基础",
  "math.linear-algebra.matrix": "矩阵基础",
  "math.linear-algebra.tensor": "张量表示",
  "math.linear-algebra.matrix-operations": "矩阵运算",
  "math.linear-algebra.matrix-multiplication": "矩阵乘法",
  "math.linear-algebra.norm": "范数与距离",
  "math.linear-algebra.eigen-decomposition": "特征分解",
  "math.linear-algebra.svd": "奇异值分解",
  "math.calculus.derivative-gradient": "导数与梯度",
  "math.calculus.chain-rule": "链式法则",
  "ml.optimization.gradient-descent": "梯度下降",
  "ml.optimization.stochastic-gradient-descent": "随机梯度下降",
  "ml.optimization.loss-function": "损失函数",
  "dl.vision.image-tensor": "图像张量",
  "dl.cnn.convolution": "卷积运算",
  "dl.cnn.cross-correlation": "互相关",
  "dl.cnn.kernel-filter": "卷积核与滤波器",
  "dl.cnn.padding-stride": "填充与步幅",
  "dl.cnn.pooling": "池化层",
  "dl.cnn.receptive-field": "局部感受野",
  "dl.cnn.architecture": "CNN 结构",
  "dl.cnn.flatten-fully-connected": "展平与全连接",
  "dl.cnn.backpropagation": "卷积网络反向传播",
  "dl.neuron.perceptron": "感知机",
  "dl.feedforward.mlp": "多层感知机",
  "dl.activation.relu": "ReLU 激活函数",
  "dl.forward-pass": "前向传播",
  "dl.computation.computational-graph": "计算图",
  "dl.backpropagation": "反向传播",
  "dl.initialization.weight-initialization": "权重初始化",
  "dl.output-layer": "输出层",
  "dl.output.softmax": "Softmax 输出",
};

const DOMAIN_MAP: Record<string, string> = {
  math: "数学基础",
  ml: "机器学习",
  dl: "深度学习",
  nlp: "自然语言处理",
  rag: "知识检索",
  practice: "实践应用",
};

const STAGE_MAP: Record<string, string> = {
  "chapter.01": "基础准备",
  "chapter.02": "核心概念",
  "chapter.03": "结构理解",
  "chapter.04": "模型训练",
  "chapter.05": "视觉应用",
  "chapter.06": "序列表示",
  "chapter.07": "架构进阶",
  "chapter.08": "模型应用",
  "chapter.09": "模型对齐",
  "chapter.10": "知识检索",
  "chapter.11": "应用实践",
};

const COURSE_ALIASES: Record<string, string> = {
  ch01_foundation: "chapter.01.math-foundations",
  ch02_ml_review: "chapter.02.classical-machine-learning",
  ch03_cnn: "chapter.05.cnn-representation",
};

const COURSE_TITLES: Record<string, string> = {
  "chapter.01.math-foundations": "数学与编程基础",
  "chapter.02.classical-machine-learning": "经典机器学习",
  "chapter.03.neural-networks": "神经网络基础",
  "chapter.04.training-and-regularization": "模型训练与正则化",
  "chapter.05.cnn-representation": "卷积神经网络（CNN）",
  "chapter.06.embeddings-and-sequences": "嵌入与序列",
  "chapter.07.transformer": "Transformer 架构",
  "chapter.08.large-language-models": "大语言模型",
  "chapter.09.alignment-and-peft": "模型对齐与参数高效微调",
  "chapter.10.rag": "检索增强生成",
  "chapter.11.rag-evaluation-and-practice": "RAG 评估与实践",
};

const COURSE_BY_CHAPTER: Record<string, string> = Object.fromEntries(
  Object.keys(COURSE_TITLES).map((id) => [chapterKey(id), id]),
);

const DIFFICULTY_MAP: Record<string, KnowledgeDifficulty> = {
  entry: "入门",
  intro: "入门",
  basic: "基础",
  intermediate: "基础",
  advanced: "进阶",
  comprehensive: "综合",
};

function shortId(id: string) {
  return id.split(".").at(-1) || id;
}

function looksLikeInternalId(value?: string) {
  return Boolean(value && /^[a-z]+(?:[._-][a-z0-9]+){2,}$/i.test(value));
}

export function knowledgeTitle(id: string, rawTitle?: string, rawName?: string) {
  const mapped = TITLE_MAP[id];
  if (mapped) return mapped;
  const raw = rawTitle || rawName;
  return raw && raw !== id && !looksLikeInternalId(raw) ? raw : humanizeConceptId(id);
}

export function humanizeConceptId(id: string) {
  const fallback = shortId(id)
    .replaceAll("-", " ")
    .replaceAll("_", " ")
    .trim();
  return fallback ? fallback.charAt(0).toUpperCase() + fallback.slice(1) : "未命名知识点";
}

export function domainTitle(id: string) {
  const prefix = id.split(".")[0] || "";
  return DOMAIN_MAP[prefix] || prefix || "课程知识";
}

export function stageTitle(chapterId?: string, sequence?: number) {
  const chapter = chapterId?.match(/^chapter\.\d+/)?.[0];
  return STAGE_MAP[chapter || ""] || (typeof sequence === "number" ? `学习阶段 ${Math.ceil(sequence / 10)}` : "课程知识");
}

export function difficultyTitle(depth?: string): KnowledgeDifficulty {
  return DIFFICULTY_MAP[depth || ""] || "基础";
}

export function courseIdFromProfile(profile?: DiagnosisProfile | LearnerSnapshot | null) {
  if (!profile) return "";
  if ("learning_scope" in profile) return profile.learning_scope?.chapter_id || "";
  return "";
}

function chapterKey(chapterId?: string) {
  if (!chapterId) return "";
  const aliased = COURSE_ALIASES[chapterId] || chapterId;
  const match = aliased.match(/(?:chapter\.)?(\d{1,2})/);
  return match ? `chapter.${match[1].padStart(2, "0")}` : aliased;
}

export function canonicalCourseId(courseId: string) {
  const aliased = COURSE_ALIASES[courseId] || courseId;
  return COURSE_TITLES[aliased] ? aliased : COURSE_BY_CHAPTER[chapterKey(aliased)] || aliased;
}

export function courseTitle(courseId: string) {
  return COURSE_TITLES[canonicalCourseId(courseId)] || "当前课程";
}

export function normalizeChapterId(chapterId?: string) {
  return chapterKey(chapterId);
}

export function isNodeInCourse(node: PathNode, courseId: string) {
  if (!courseId) return true;
  return normalizeChapterId(node.chapter_id) === normalizeChapterId(courseId);
}

function masteryForNode(
  node: PathNode,
  profile?: DiagnosisProfile | null,
  snapshot?: LearnerSnapshot | null,
) {
  if (typeof node.mastery_score === "number") return clampMastery(node.mastery_score);
  const snapshotPoint = snapshot?.knowledge_mastery.find((item) => item.concept_id === node.concept_id);
  if (snapshotPoint) return clampMastery(snapshotPoint.mastery_score);
  const profilePoint = profile?.knowledge_mastery?.points?.[node.concept_id];
  return clampMastery(profilePoint?.mastery);
}

function hasEvidence(node: PathNode, profile?: DiagnosisProfile | null, snapshot?: LearnerSnapshot | null) {
  return typeof masteryForNode(node, profile, snapshot) === "number"
    || Boolean(snapshot?.knowledge_mastery.some((item) => item.concept_id === node.concept_id))
    || Boolean(profile?.knowledge_mastery?.points?.[node.concept_id]);
}

function hasStarted(node: PathNode) {
  return ["in_progress", "learning", "active", "started"].includes(node.status);
}

function isSourceCompleted(node: PathNode) {
  return ["completed", "done"].includes(node.status);
}

function sourcePrerequisites(node: PathNode) {
  return node.hard_prerequisite_ids || node.prerequisite_ids || [];
}

function progressForNode(node: PathNode, progress?: LearningProgress | null) {
  return progress?.concept_id === node.concept_id ? progress : null;
}

function completionRateForNode(node: PathNode, progress?: LearningProgress | null) {
  const currentProgress = progressForNode(node, progress);
  if (currentProgress) return currentProgress.lecture_completed ? 1 : currentProgress.lecture_progress || 0;
  return isSourceCompleted(node) ? 1 : hasStarted(node) ? 0.25 : 0;
}

function progressStatusForNode(
  node: PathNode,
  mastery: number | null,
  progress?: LearningProgress | null,
): KnowledgeNode["progressStatus"] {
  const currentProgress = progressForNode(node, progress);
  if (mastery !== null && mastery >= MASTERY_THRESHOLD && (currentProgress?.assessment_passed || isSourceCompleted(node))) return "mastered";
  if (mastery !== null && mastery < MASTERY_THRESHOLD && currentProgress?.assessment_attempts) return currentProgress.remediation_required ? "needs_review" : "assessed";
  if (currentProgress?.lecture_completed || (isSourceCompleted(node) && mastery === null)) return "completed";
  if (currentProgress?.lecture_progress || hasStarted(node)) return "learning";
  return "not_started";
}

function isUnlockReady(node?: KnowledgeNode) {
  if (!node) return false;
  if (DEFAULT_UNLOCK_POLICY === "completion_based") {
    return node.progressStatus === "completed" || node.progressStatus === "mastered" || node.completionRate >= 1 || (node.mastery ?? 0) >= UNLOCK_THRESHOLD;
  }
  return (node.effectiveMastery ?? node.mastery ?? 0) >= UNLOCK_THRESHOLD;
}

function statusForNode(
  node: PathNode,
  byId: Map<string, KnowledgeNode>,
  profile?: DiagnosisProfile | null,
  snapshot?: LearnerSnapshot | null,
  progress?: LearningProgress | null,
): KnowledgeStatus {
  const mastery = masteryForNode(node, profile, snapshot);
  const prerequisites = sourcePrerequisites(node);
  const prerequisitesReady = prerequisites.every((id) => isUnlockReady(byId.get(id)));
  const currentProgress = progressForNode(node, progress);

  if (mastery !== null && mastery >= MASTERY_THRESHOLD && (isSourceCompleted(node) || currentProgress?.assessment_passed || hasEvidence(node, profile, snapshot))) {
    return "mastered";
  }
  if (currentProgress?.lecture_completed || (isSourceCompleted(node) && mastery === null)) return "completed";
  if (hasStarted(node)) return "learning";
  if (!hasEvidence(node, profile, snapshot)) return prerequisitesReady ? "unevaluated" : "locked";
  if (!prerequisitesReady) return "locked";
  return ["available", "pending"].includes(node.status) ? "available" : "unevaluated";
}

function recommendationScore(node: KnowledgeNode, byId: Map<string, KnowledgeNode>) {
  const masteryGap = node.mastery === null ? 1 : 1 - node.mastery;
  const prerequisites = node.prerequisiteIds;
  const prerequisiteReadiness = prerequisites.length
    ? prerequisites.filter((id) => (byId.get(id)?.mastery ?? 0) >= UNLOCK_THRESHOLD).length / prerequisites.length
    : 1;
  const pathCost = Math.min((node.estimatedMinutes || 30) / 180, 1);
  const statusBonus = node.status === "learning" ? 0.35 : node.status === "available" || node.status === "unevaluated" ? 0.2 : 0;
  return masteryGap * 0.45 + prerequisiteReadiness * 0.3 + statusBonus - pathCost * 0.08;
}

function recommendationPath(node: KnowledgeNode, byId: Map<string, KnowledgeNode>) {
  const result: string[] = [];
  const visiting = new Set<string>();
  const seen = new Set<string>();
  function visit(current: KnowledgeNode) {
    if (visiting.has(current.id)) return;
    visiting.add(current.id);
    for (const prerequisiteId of current.prerequisiteIds) {
      const prerequisite = byId.get(prerequisiteId);
      if (prerequisite) visit(prerequisite);
    }
    if (!seen.has(current.id)) {
      result.push(current.id);
      seen.add(current.id);
    }
    visiting.delete(current.id);
  }
  visit(node);
  return result;
}

export function adaptPathNodes(
  rawNodes: PathNode[],
  options: {
    courseId: string;
    profile?: DiagnosisProfile | null;
    snapshot?: LearnerSnapshot | null;
    learningProgress?: LearningProgress | null;
  },
) {
  const scoped = rawNodes.filter((node) => isNodeInCourse(node, options.courseId));
  const courseId = canonicalCourseId(options.courseId);
  const base = scoped.map<KnowledgeNode>((node) => {
    const mastery = masteryForNode(node, options.profile, options.snapshot);
    const progressStatus = progressStatusForNode(node, mastery, options.learningProgress);
    const completionRate = completionRateForNode(node, options.learningProgress);
    return {
      id: node.concept_id,
      courseId,
      title: knowledgeTitle(node.concept_id, node.title, node.name),
      shortTitle: knowledgeTitle(node.concept_id, node.title, node.name),
      description: node.summary,
      domain: domainTitle(node.concept_id),
      stage: stageTitle(node.chapter_id, node.sequence),
      difficulty: difficultyTitle(node.depth || node.delivery_depth),
      estimatedMinutes: node.estimated_minutes,
      mastery,
      status: "unevaluated",
      progressStatus,
      completionRate,
      effectiveMastery: mastery,
      unmetPrerequisiteIds: [],
      isUnlocked: false,
      isRecommended: false,
      prerequisiteIds: sourcePrerequisites(node),
      resourceCount: 0,
      assessmentCount: options.profile?.knowledge_mastery?.points?.[node.concept_id]?.test_count,
      lastStudiedAt: options.snapshot?.knowledge_mastery.find((item) => item.concept_id === node.concept_id)?.observed_at || undefined,
      reasonCodes: node.reason_codes || [],
      source: node,
    };
  });
  const byId = new Map(base.map((node) => [node.id, node]));
  base.forEach((node) => {
    node.unmetPrerequisiteIds = node.prerequisiteIds.filter((id) => !isUnlockReady(byId.get(id)));
    node.isUnlocked = node.unmetPrerequisiteIds.length === 0;
    node.status = statusForNode(node.source, byId, options.profile, options.snapshot, options.learningProgress);
  });

  const hasCourseEvidence = base.some((node) =>
    node.mastery !== null || hasStarted(node.source) || ["available", "completed", "done"].includes(node.source.status),
  );
  const candidate = hasCourseEvidence
    ? base
      .filter((node) => ["available", "learning", "unevaluated"].includes(node.status))
      .sort((a, b) => recommendationScore(b, byId) - recommendationScore(a, byId))[0]
    : undefined;
  if (candidate) {
    candidate.status = "recommended";
    candidate.isRecommended = true;
    for (const prerequisite of candidate.prerequisiteIds) {
      const item = byId.get(prerequisite);
      if (item?.status === "available") item.status = "available";
    }
  }

  const edges: KnowledgeEdge[] = [];
  base.forEach((node) => {
    node.prerequisiteIds.forEach((source) => {
      edges.push({
        id: `${source}->${node.id}`,
        source,
        target: node.id,
        relation: candidate && summaryPathIncludes(candidate, byId, source, node.id) ? "recommended" : "prerequisite",
      });
    });
  });

  const summary: LearningPathSummary = {
    courseId: options.courseId,
    totalNodes: base.length,
    masteredNodes: base.filter((node) => node.status === "mastered").length,
    availableNodes: base.filter((node) => ["available", "recommended", "learning", "unevaluated"].includes(node.status)).length,
    lockedNodes: base.filter((node) => node.status === "locked").length,
    averageMastery: (() => {
      const values = base.map((node) => node.mastery).filter((value): value is number => typeof value === "number");
      return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
    })(),
    estimatedRemainingMinutes: (() => {
      const values = base
        .filter((node) => node.status !== "mastered")
        .map((node) => node.estimatedMinutes)
        .filter((value): value is number => typeof value === "number");
      return values.length ? values.reduce((sum, value) => sum + value, 0) : null;
    })(),
    recommendedNodeId: candidate?.id || null,
    recommendedPathNodeIds: candidate ? recommendationPath(candidate, byId) : [],
  };

  return { nodes: base, edges, summary };
}

function summaryPathIncludes(
  candidate: KnowledgeNode,
  byId: Map<string, KnowledgeNode>,
  sourceId: string,
  targetId: string,
) {
  const pathIds = new Set(recommendationPath(candidate, byId));
  return pathIds.has(sourceId) && pathIds.has(targetId);
}
