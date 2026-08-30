export interface PathNode {
  concept_id: string;
  title?: string;
  name?: string;
  summary?: string;
  status: string;
  mastery_score?: number | null;
  confidence?: number;
  depth?: string;
  estimated_minutes?: number;
  prerequisite_ids?: string[];
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
  handoff?: Record<string, unknown> | null;
  retrieval?: Record<string, unknown> | null;
  evidence_gap?: Record<string, unknown> | null;
  failure?: { code: string; message: string; retryable?: boolean };
  steps?: Array<{ stage: string; status: string; failure?: unknown }>;
}
import type { LearnerSnapshot } from "./learner";
