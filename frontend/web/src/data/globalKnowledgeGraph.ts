import { reactive } from "vue";
import { courseKnowledgeBase } from "./courseKnowledgeBase";

export type SystemNodeType = "subject" | "course" | "chapter" | "knowledge_point";
export type SystemRelation = "prerequisite" | "contains" | "related" | "applies_to";
export type LearningOverlayStatus = "not_started" | "in_progress" | "completed_unassessed" | "mastered" | "review_recommended";

export interface SystemKnowledgeNode {
  id: string;
  name: string;
  type: SystemNodeType;
  subjectId: string;
  courseId?: string;
  chapterId?: string;
  description?: string;
  tags: string[];
  aliases: string[];
  position: { x: number; y: number };
  resourceCount?: number;
  assessmentCount?: number;
  estimatedMinutes?: number;
}

export interface SystemKnowledgeEdge {
  id: string;
  sourceId: string;
  targetId: string;
  relation: SystemRelation;
  description: string;
}

export interface SubjectOption {
  id: string;
  name: string;
}

export interface CourseOption {
  id: string;
  name: string;
  subjectId: string;
}

const subjectOptions: SubjectOption[] = [
  { id: "all", name: "全部知识" },
  { id: "ai", name: "人工智能" },
  { id: "math", name: "数学基础" },
  { id: "cs", name: "计算机基础" },
  { id: "data", name: "数据科学" },
];

const courseOptions: CourseOption[] = [
  { id: "all", name: "全部课程", subjectId: "all" },
  { id: courseKnowledgeBase.id, name: courseKnowledgeBase.currentTrack, subjectId: "ai" },
];

const nodePosition: Record<string, { x: number; y: number }> = {
  ai: { x: 520, y: 270 },
  math: { x: 170, y: 150 },
  cs: { x: 130, y: 420 },
  data: { x: 690, y: 120 },
  [courseKnowledgeBase.id]: { x: 520, y: 350 },
  "chapter.01.math-foundations": { x: 230, y: 300 },
  "chapter.02.classical-machine-learning": { x: 500, y: 520 },
  "chapter.03.neural-networks": { x: 770, y: 330 },
  "chapter.04.training-and-regularization": { x: 850, y: 500 },
  "chapter.05.cnn-representation": { x: 650, y: 690 },
  "chapter.06.embeddings-and-sequences": { x: 360, y: 690 },
  "math.linear-algebra.scalar": { x: 150, y: 260 },
  "math.linear-algebra.vector": { x: 170, y: 355 },
  "math.linear-algebra.matrix": { x: 260, y: 410 },
  "math.calculus.derivative-gradient": { x: 300, y: 245 },
  "ml.optimization.loss-function": { x: 410, y: 475 },
  "ml.optimization.gradient-descent": { x: 560, y: 600 },
  "dl.vision.image-tensor": { x: 400, y: 350 },
  "dl.cnn.convolution": { x: 520, y: 430 },
  "dl.cnn.padding-stride": { x: 675, y: 430 },
  "dl.cnn.pooling": { x: 765, y: 515 },
  "dl.cnn.receptive-field": { x: 680, y: 570 },
  "dl.cnn.cross-correlation": { x: 430, y: 590 },
  "dl.neuron.perceptron": { x: 750, y: 260 },
  "dl.activation.relu": { x: 860, y: 230 },
};

function point(id: string, fallbackIndex = 0) {
  return nodePosition[id] || { x: 220 + (fallbackIndex % 5) * 140, y: 220 + Math.floor(fallbackIndex / 5) * 110 };
}

function subjectForKnowledge(id: string) {
  if (id.startsWith("math.")) return "math";
  if (id.startsWith("ml.") || id.startsWith("dl.")) return "ai";
  if (id.includes("tensor") || id.includes("data")) return "data";
  return "cs";
}

const chapterNodes: SystemKnowledgeNode[] = courseKnowledgeBase.chapters.map((chapter) => ({
  id: chapter.id,
  name: `第${String(chapter.order).padStart(2, "0")}章 · ${chapter.title}`,
  type: "chapter",
  subjectId: "ai",
  courseId: courseKnowledgeBase.id,
  chapterId: chapter.id,
  description: chapter.subtitle,
  tags: ["章节", chapter.title],
  aliases: [chapter.subtitle],
  position: point(chapter.id),
}));

const knowledgeNodes: SystemKnowledgeNode[] = courseKnowledgeBase.chapters.flatMap((chapter) =>
  chapter.nodes.map((node, index) => ({
    id: node.id,
    name: node.title,
    type: "knowledge_point" as const,
    subjectId: subjectForKnowledge(node.id),
    courseId: courseKnowledgeBase.id,
    chapterId: chapter.id,
    description: node.summary,
    tags: [chapter.title, node.title],
    aliases: [node.summary],
    position: point(node.id, index),
    resourceCount: node.lectures + node.examples + node.exercises,
    assessmentCount: node.assessments,
    estimatedMinutes: node.estimatedMinutes,
  })),
);

const objectiveNodes: SystemKnowledgeNode[] = [
  ...subjectOptions.filter((item) => item.id !== "all").map((subject) => ({
    id: subject.id,
    name: subject.name,
    type: "subject" as const,
    subjectId: subject.id,
    description: `${subject.name}相关课程与知识点集合。`,
    tags: ["学科"],
    aliases: [],
    position: point(subject.id),
  })),
  {
    id: courseKnowledgeBase.id,
    name: courseKnowledgeBase.currentTrack,
    type: "course" as const,
    subjectId: "ai",
    courseId: courseKnowledgeBase.id,
    description: "围绕卷积神经网络的核心概念、先修知识与视觉应用建立知识关系。",
    tags: ["课程", "CNN", "计算机视觉"],
    aliases: [courseKnowledgeBase.title],
    position: point(courseKnowledgeBase.id),
  },
  ...chapterNodes,
  ...knowledgeNodes,
];

const containsEdges: SystemKnowledgeEdge[] = [
  { id: "ai-contains-course", sourceId: "ai", targetId: courseKnowledgeBase.id, relation: "contains", description: "人工智能学科包含卷积神经网络课程。" },
  ...courseKnowledgeBase.chapters.map((chapter) => ({
    id: `${courseKnowledgeBase.id}-contains-${chapter.id}`,
    sourceId: courseKnowledgeBase.id,
    targetId: chapter.id,
    relation: "contains" as const,
    description: "课程包含章节。",
  })),
  ...courseKnowledgeBase.chapters.flatMap((chapter) =>
    chapter.nodes.map((node) => ({
      id: `${chapter.id}-contains-${node.id}`,
      sourceId: chapter.id,
      targetId: node.id,
      relation: "contains" as const,
      description: "章节包含知识点。",
    })),
  ),
];

const prerequisiteEdges: SystemKnowledgeEdge[] = courseKnowledgeBase.chapters.flatMap((chapter) =>
  chapter.nodes.flatMap((node) =>
    node.prerequisites.map((sourceId) => ({
      id: `${sourceId}-prerequisite-${node.id}`,
      sourceId,
      targetId: node.id,
      relation: "prerequisite" as const,
      description: `${sourceId} 是 ${node.title} 的先修知识。`,
    })),
  ),
);

const relatedEdges: SystemKnowledgeEdge[] = [
  ["math.linear-algebra.matrix", "dl.vision.image-tensor"],
  ["ml.optimization.loss-function", "ml.optimization.gradient-descent"],
  ["dl.cnn.convolution", "dl.cnn.cross-correlation"],
  ["dl.cnn.padding-stride", "dl.cnn.receptive-field"],
  ["dl.neuron.perceptron", "dl.activation.relu"],
].map(([sourceId, targetId]) => ({
  id: `${sourceId}-related-${targetId}`,
  sourceId,
  targetId,
  relation: "related" as const,
  description: "两个知识点在课程理解中高度相关。",
}));

const applicationEdges: SystemKnowledgeEdge[] = [
  ["dl.cnn.convolution", "dl.cnn.pooling"],
  ["dl.cnn.convolution", "dl.cnn.receptive-field"],
  ["dl.vision.image-tensor", "dl.cnn.convolution"],
].map(([sourceId, targetId]) => ({
  id: `${sourceId}-applies-${targetId}`,
  sourceId,
  targetId,
  relation: "applies_to" as const,
  description: "源知识可用于理解或应用目标知识。",
}));

export const globalKnowledgeGraph = reactive({
  subjects: subjectOptions,
  courses: courseOptions,
  nodes: objectiveNodes,
  edges: [...containsEdges, ...prerequisiteEdges, ...relatedEdges, ...applicationEdges],
});

export function refreshGlobalKnowledgeGraph() {
  const chapterNodes: SystemKnowledgeNode[] = courseKnowledgeBase.chapters.map((chapter) => ({
    id: chapter.id,
    name: `第${String(chapter.order).padStart(2, "0")}章 · ${chapter.title}`,
    type: "chapter",
    subjectId: "ai",
    courseId: courseKnowledgeBase.id,
    chapterId: chapter.id,
    description: chapter.subtitle,
    tags: ["章节", chapter.title],
    aliases: [chapter.subtitle],
    position: point(chapter.id),
  }));
  const knowledgeNodes: SystemKnowledgeNode[] = courseKnowledgeBase.chapters.flatMap((chapter) =>
    chapter.nodes.map((node, index) => ({
      id: node.id,
      name: node.title,
      type: "knowledge_point" as const,
      subjectId: subjectForKnowledge(node.id),
      courseId: courseKnowledgeBase.id,
      chapterId: chapter.id,
      description: node.summary,
      tags: [chapter.title, node.title],
      aliases: [node.summary],
      position: point(node.id, index),
      resourceCount: node.lectures + node.examples + node.exercises,
      assessmentCount: node.assessments,
      estimatedMinutes: node.estimatedMinutes,
    })),
  );
  const nodes: SystemKnowledgeNode[] = [
    ...subjectOptions.filter((item) => item.id !== "all").map((subject) => ({
      id: subject.id,
      name: subject.name,
      type: "subject" as const,
      subjectId: subject.id,
      description: `${subject.name}相关课程与知识点集合。`,
      tags: ["学科"],
      aliases: [],
      position: point(subject.id),
    })),
    {
      id: courseKnowledgeBase.id,
      name: courseKnowledgeBase.currentTrack,
      type: "course" as const,
      subjectId: "ai",
      courseId: courseKnowledgeBase.id,
      description: courseKnowledgeBase.subtitle,
      tags: ["课程"],
      aliases: [courseKnowledgeBase.title],
      position: point(courseKnowledgeBase.id),
    },
    ...chapterNodes,
    ...knowledgeNodes,
  ];
  const contains: SystemKnowledgeEdge[] = [
    { id: "ai-contains-course", sourceId: "ai", targetId: courseKnowledgeBase.id, relation: "contains", description: "人工智能学科包含课程。" },
    ...courseKnowledgeBase.chapters.map((chapter) => ({
      id: `${courseKnowledgeBase.id}-contains-${chapter.id}`,
      sourceId: courseKnowledgeBase.id,
      targetId: chapter.id,
      relation: "contains" as const,
      description: "课程包含章节。",
    })),
    ...courseKnowledgeBase.chapters.flatMap((chapter) => chapter.nodes.map((node) => ({
      id: `${chapter.id}-contains-${node.id}`,
      sourceId: chapter.id,
      targetId: node.id,
      relation: "contains" as const,
      description: "章节包含知识点。",
    }))),
  ];
  const prerequisites: SystemKnowledgeEdge[] = courseKnowledgeBase.chapters.flatMap((chapter) =>
    chapter.nodes.flatMap((node) => node.prerequisites.map((sourceId) => ({
      id: `${sourceId}-prerequisite-${node.id}`,
      sourceId,
      targetId: node.id,
      relation: "prerequisite" as const,
      description: `${sourceId} 是 ${node.title} 的先修知识。`,
    }))),
  );
  globalKnowledgeGraph.nodes.splice(0, globalKnowledgeGraph.nodes.length, ...nodes);
  globalKnowledgeGraph.edges.splice(0, globalKnowledgeGraph.edges.length, ...contains, ...prerequisites, ...relatedEdges, ...applicationEdges);
}
