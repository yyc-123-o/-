import type { PathNode } from "./planning";

export type KnowledgeStatus =
  | "mastered"
  | "completed"
  | "learning"
  | "available"
  | "recommended"
  | "locked"
  | "unevaluated";

export type KnowledgeDifficulty = "入门" | "基础" | "进阶" | "综合";

export interface KnowledgeNode {
  id: string;
  courseId: string;
  title: string;
  shortTitle?: string;
  description?: string;
  domain: string;
  stage?: string;
  difficulty: KnowledgeDifficulty;
  estimatedMinutes?: number;
  mastery: number | null;
  status: KnowledgeStatus;
  progressStatus: "not_started" | "learning" | "completed" | "assessed" | "mastered" | "needs_review";
  completionRate: number;
  effectiveMastery: number | null;
  unmetPrerequisiteIds: string[];
  isUnlocked: boolean;
  isRecommended: boolean;
  prerequisiteIds: string[];
  resourceCount: number;
  assessmentCount?: number;
  lastStudiedAt?: string;
  reasonCodes: string[];
  source: PathNode;
}

export interface KnowledgeEdge {
  id: string;
  source: string;
  target: string;
  relation: "prerequisite" | "recommended" | "related";
}

export interface LearningPathSummary {
  courseId: string;
  totalNodes: number;
  masteredNodes: number;
  availableNodes: number;
  lockedNodes: number;
  averageMastery: number | null;
  estimatedRemainingMinutes: number | null;
  recommendedNodeId: string | null;
  recommendedPathNodeIds: string[];
}
