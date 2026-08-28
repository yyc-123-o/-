export interface LearnerSummary {
  id: string;
  name: string;
  education_level: string;
  major: string;
  test_count: number;
  interaction_count: number;
}

export interface MasteryPoint {
  concept_id: string;
  mastery_score: number | null;
  assessment_status: "assessed" | "not_assessed";
  confidence: number;
  observed_at?: string | null;
  evidence_refs?: string[];
}

export interface AbilityScore {
  score: number;
  confidence: number;
  assessment_run_id: string;
}

export interface LearnerSnapshot {
  schema_version: string;
  profile_id: string;
  learner_ref: string;
  graph_version: string;
  generated_at?: string | null;
  assessment_runs: string[];
  knowledge_mastery: MasteryPoint[];
  abilities: Record<string, AbilityScore>;
  error_patterns: Array<{
    code: string;
    count: number;
    ratio: number;
    concept_ids: string[];
    evidence_refs: string[];
  }>;
  preferences: {
    content_order: string[];
    code_language?: string | null;
    framework?: string | null;
    presentation: string[];
    pace_hours_per_week?: number | null;
    project_orientation?: string | null;
  };
}

export interface DiagnosisProfile {
  profile_id: string;
  profile_version?: string;
  learner_id: string;
  learner: {
    name: string;
    education?: {
      level?: string;
      major?: string;
      institution?: string;
      gpa?: number | null;
    };
    self_assessment?: {
      learning_goal?: string;
      weekly_hours?: number;
    };
  };
  knowledge_mastery?: {
    global_theta?: number;
    overall_accuracy?: number;
    points?: Record<string, {
      name: string;
      domain: string;
      mastery: number;
      status: string;
      confidence: number;
    }>;
    domain_summary?: Record<string, { mean_mastery: number; kps_covered: number }>;
  };
  ability_level?: {
    overall?: string;
    global_theta?: number;
    sub_dimensions?: Record<string, { score: number; level: string; confidence: number }>;
  };
  knowledge_gaps?: Array<{
    kp_id: string;
    kp_name: string;
    domain: string;
    mastery: number;
    gap_type: string;
    priority: string;
    description?: string;
    suggested_action?: string;
    confidence?: number;
  }>;
  evidence?: Array<{ claim: string; source: string; detail: string; confidence: number }>;
  diagnosis_summary?: { short?: string; full?: string; profile_confidence?: string };
  learning_scope?: {
    chapter_id?: string;
    chapter_name?: string;
    primary_kp_id?: string;
    primary_kp_name?: string;
    target_depth?: string;
    estimated_hours?: number;
  };
  meta?: { total_test_count?: number; total_interaction_count?: number };
}
