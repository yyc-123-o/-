export interface BasicForm {
  name: string;
  education: { level: string; major: string; institution: string; gpa: number | null };
  learning_goal: string;
  weekly_hours: number;
}

export interface DomainAssessment {
  domain: string;
  courses: Array<{ name: string; level: string; note?: string; kp_id?: string }>;
  note?: string;
}

export interface AdaptiveSession {
  session_id: string;
  learner_id?: string;
  next_question?: {
    question_id: string;
    question_text?: string;
    options?: string[];
    correct_answer?: number;
    knowledge_point_id?: string;
    knowledge_point_name?: string;
  };
  current_domain?: string;
  current_tier?: string;
  current_theta?: number;
  standard_error?: number | null;
  estimator_method?: string;
  item_calibration_status?: "provisional" | "calibrated";
  selection_reason?: string;
  question_count: number;
  finished?: boolean;
  final_theta?: number;
  stop_reason?: string;
  last_correct?: boolean;
  covered_kp?: number;
  total_kp?: number;
  coverage_target?: string;
  answers?: unknown[];
}
