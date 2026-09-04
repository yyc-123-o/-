import {
  BookOpen,
  ClipboardCheck,
  FileCheck2,
  FileText,
  Play,
  type LucideIcon,
} from "lucide-vue-next";
import { courseKnowledgeBase } from "@/data/courseKnowledgeBase";
import type { CourseChapter, CourseKnowledgeNode } from "@/data/courseKnowledgeBase";

export type LearningResourceType = "lecture" | "video" | "example" | "practice" | "assessment";
export type LearningResourceStatus = "not_started" | "learning" | "completed";
export type LearningResourceDifficulty = "basic" | "standard" | "advanced";

export interface LearningResource {
  id: string;
  title: string;
  type: LearningResourceType;
  typeLabel: string;
  courseId: string;
  courseTitle: string;
  chapterId: string;
  chapterTitle: string;
  knowledgePointIds: string[];
  knowledgePointTitle: string;
  duration: number;
  questionCount: number;
  difficulty: LearningResourceDifficulty;
  status: LearningResourceStatus;
  favorite: boolean;
  updatedAt: string;
  icon: LucideIcon;
}

const typeMeta: Record<LearningResourceType, { label: string; icon: LucideIcon }> = {
  lecture: { label: "讲义", icon: FileText },
  video: { label: "视频", icon: Play },
  example: { label: "示例", icon: BookOpen },
  practice: { label: "练习", icon: ClipboardCheck },
  assessment: { label: "测评", icon: FileCheck2 },
};

export function resourceIdFor(nodeId: string, type: LearningResourceType) {
  return `${encodeURIComponent(nodeId)}.${type}`;
}

export function buildResourceCatalog() {
  return courseKnowledgeBase.chapters.flatMap((chapter) =>
    chapter.nodes.flatMap((node) => resourcesForKnowledgeNode(node, chapter)),
  );
}

export function resourcesForKnowledgeNode(node: CourseKnowledgeNode, chapter = chapterForNode(node)) {
  const courseTitle = courseKnowledgeBase.currentTrack || courseKnowledgeBase.title;
  const resources: LearningResource[] = [
    {
      id: resourceIdFor(node.id, "lecture"),
      title: `${node.title}工作原理`,
      type: "lecture",
      typeLabel: typeMeta.lecture.label,
      courseId: courseKnowledgeBase.id,
      courseTitle,
      chapterId: node.chapterId,
      chapterTitle: chapter?.title || "未分章",
      knowledgePointIds: [node.id],
      knowledgePointTitle: node.title,
      duration: node.estimatedMinutes,
      questionCount: 0,
      difficulty: "standard",
      status: "not_started",
      favorite: false,
      updatedAt: "2026-09-03",
      icon: typeMeta.lecture.icon,
    },
    {
      id: resourceIdFor(node.id, "video"),
      title: `${node.title}视频讲解`,
      type: "video",
      typeLabel: typeMeta.video.label,
      courseId: courseKnowledgeBase.id,
      courseTitle,
      chapterId: node.chapterId,
      chapterTitle: chapter?.title || "未分章",
      knowledgePointIds: [node.id],
      knowledgePointTitle: node.title,
      duration: Math.max(8, Math.round(node.estimatedMinutes * 0.6)),
      questionCount: 0,
      difficulty: "basic",
      status: "not_started",
      favorite: false,
      updatedAt: "2026-09-03",
      icon: typeMeta.video.icon,
    },
    {
      id: resourceIdFor(node.id, "example"),
      title: `${node.title}可视化示例`,
      type: "example",
      typeLabel: typeMeta.example.label,
      courseId: courseKnowledgeBase.id,
      courseTitle,
      chapterId: node.chapterId,
      chapterTitle: chapter?.title || "未分章",
      knowledgePointIds: [node.id],
      knowledgePointTitle: node.title,
      duration: Math.max(6, Math.round(node.estimatedMinutes * 0.45)),
      questionCount: 0,
      difficulty: "basic",
      status: "not_started",
      favorite: false,
      updatedAt: "2026-09-03",
      icon: typeMeta.example.icon,
    },
    {
      id: resourceIdFor(node.id, "practice"),
      title: `${node.title}巩固练习`,
      type: "practice",
      typeLabel: typeMeta.practice.label,
      courseId: courseKnowledgeBase.id,
      courseTitle,
      chapterId: node.chapterId,
      chapterTitle: chapter?.title || "未分章",
      knowledgePointIds: [node.id],
      knowledgePointTitle: node.title,
      duration: Math.max(10, Math.round(node.estimatedMinutes * 0.7)),
      questionCount: node.exercises,
      difficulty: "standard",
      status: "not_started",
      favorite: false,
      updatedAt: "2026-09-03",
      icon: typeMeta.practice.icon,
    },
    {
      id: resourceIdFor(node.id, "assessment"),
      title: `${node.title}单元测评`,
      type: "assessment",
      typeLabel: typeMeta.assessment.label,
      courseId: courseKnowledgeBase.id,
      courseTitle,
      chapterId: node.chapterId,
      chapterTitle: chapter?.title || "未分章",
      knowledgePointIds: [node.id],
      knowledgePointTitle: node.title,
      duration: 12,
      questionCount: node.assessments,
      difficulty: "standard",
      status: "not_started",
      favorite: false,
      updatedAt: "2026-09-03",
      icon: typeMeta.assessment.icon,
    },
  ];

  return resources.filter((resource) => {
    if (resource.type === "lecture") return node.lectures > 0;
    if (resource.type === "video") return node.lectures > 0;
    if (resource.type === "example") return node.examples > 0;
    if (resource.type === "practice") return node.exercises > 0;
    return node.assessments > 0;
  });
}

export function findResourceById(resourceId: string) {
  return buildResourceCatalog().find((resource) => resource.id === resourceId) || null;
}

export function firstResourceForKnowledgePoint(knowledgePointId: string, preferredType: LearningResourceType = "lecture") {
  const resources = buildResourceCatalog().filter((resource) => resource.knowledgePointIds.includes(knowledgePointId));
  return resources.find((resource) => resource.type === preferredType) || resources[0] || null;
}

export function chapterForNode(node: CourseKnowledgeNode) {
  return courseKnowledgeBase.chapters.find((chapter: CourseChapter) => chapter.id === node.chapterId);
}
