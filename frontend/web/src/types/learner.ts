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
    standard_error?: number | null;
    estimation_method?: string;
    overall_accuracy?: number;
    overall_mastery?: number | null;
    overall_confidence?: number;
    tested_kps?: number;
    total_kps?: number;
    coverage_ratio?: number;
    points?: Record<string, {
      name: string;
      domain: string;
      mastery: number | null;
      status: string;
      test_count?: number;
      confidence: number;
      standard_error?: number | null;
      evidence_level?: "none" | "self_report" | "preliminary" | "limited" | "stable";
    }>;
    domain_summary?: Record<string, {
      mean_mastery: number | null;
      kps_covered: number;
      total_kps?: number;
      tested_kps?: number;
      evidence_confidence?: number;
    }>;
  };
  ability_level?: {
    overall?: string;
    global_theta?: number;
    sub_dimensions?: Record<string, { score: number | null; level: string; confidence: number }>;
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

export interface OutcomeMetric {
  before: number;
  after: number;
  delta: number;
}

export interface OutcomeDomainChange {
  domain: string;
  before: number;
  after: number;
  delta: number;
}

export interface OutcomeKpChange {
  kp_id: string;
  name: string;
  domain: string;
  before: number | null;
  after: number | null;
  delta: number;
  category: string;
}

export interface OutcomeGapChange {
  kp_id: string;
  name: string;
  domain: string;
  before: number;
  after: number;
}

export interface OutcomeErrorPatternChange {
  category: string;
  before_ratio: number;
  after_ratio: number;
  delta: number;
}

export interface LearningOutcomeReport {
  report_id: string;
  learner_id: string;
  chapter_id: string;
  baseline_profile_id: string;
  post_profile_id: string;
  overall_verdict: string;
  theta: Partial<OutcomeMetric>;
  accuracy: Partial<OutcomeMetric>;
  ability_level: { before?: string; after?: string };
  domain_changes: OutcomeDomainChange[];
  kp_changes: OutcomeKpChange[];
  gaps_resolved: OutcomeGapChange[];
  gaps_remaining: OutcomeGapChange[];
  gaps_new: OutcomeGapChange[];
  error_pattern_changes: OutcomeErrorPatternChange[];
  recommendation: string;
}
