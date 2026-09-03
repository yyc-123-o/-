export interface PathNode {
  concept_id: string;
  chapter_id?: string;
  section_id?: string;
  sequence?: number;
  title?: string;
  name?: string;
  summary?: string;
  status: string;
  delivery_depth?: string;
  mastery_score?: number | null;
  confidence?: number;
  depth?: string;
  estimated_minutes?: number;
  prerequisite_ids?: string[];
  hard_prerequisite_ids?: string[];
  blocking_prerequisite_ids?: string[];
  reason_codes?: string[];
}

export interface LearningProgress {
  concept_id: string;
  lecture_progress: number;
  lecture_completed: boolean;
  practice_completed: boolean;
  assessment_passed: boolean;
  assessment_attempts: number;
  failed_attempts: number;
  remediation_required: boolean;
  can_complete?: boolean;
}

export interface PlatformRun {
  run_id: string;
  profile_id: string;
  profile?: LearnerSnapshot | null;
  status: string;
  planning?: {
    path?: { nodes: PathNode[]; profile_id?: string };
    current_node?: PathNode;
    adaptations?: Record<string, unknown>;
  };
  resources?: Record<string, unknown> | null;
  handoff?: { concept_id?: string; chapter_id?: string; [key: string]: unknown } | null;
  retrieval?: Record<string, unknown> | null;
  evidence_gap?: Record<string, unknown> | null;
  failure?: { code: string; message: string; retryable?: boolean };
  steps?: Array<{ stage: string; status: string; failure?: unknown }>;
  learning_progress?: LearningProgress | null;
}
import type { LearnerSnapshot } from "./learner";
