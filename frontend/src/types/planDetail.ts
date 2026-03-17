export interface PlanMetricsByService {
  service: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens?: number;
  estimated_cost_prompt_usd?: number;
  estimated_cost_completion_usd?: number;
  estimated_cost_total_usd?: number;
}

export interface PlanMetrics {
  plan_id: string;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  estimated_cost_prompt_usd?: number;
  estimated_cost_completion_usd?: number;
  estimated_cost_total_usd?: number;
  pipeline_status?: string;
  first_event_at?: string | null;
  last_event_at?: string | null;
  duration_seconds?: number;
  qa_retry_count?: number;
  qa_failed_count?: number;
  security_blocked_count?: number;
  replan_suggestions_count?: number;
  replan_confirmed_count?: number;
  by_service: PlanMetricsByService[];
}

export interface PlanTaskSummary {
  task_id: string;
  file_path: string;
  language: string;
  group_id: string;
  status: string;
  qa_attempt: number;
  code?: string;
  dev_reasoning?: string;
  code_history?: { qa_attempt: number; code: string }[];
}

export interface PlanModuleSummary {
  group_id: string;
  tasks_count: number;
  qa_failed_count: number;
  max_severity_hint: string;
}

export interface QAOutcome {
  task_id: string;
  module: string;
  severity_hint: string;
  issues: string[];
  reasoning: string;
  qa_attempt: number;
}

export interface SecurityOutcome {
  approved: boolean;
  severity_hint: string;
  violations: string[];
  reasoning: string;
  files_scanned: number;
}

export interface ReplanItem {
  event_type: string;
  severity: string;
  reason: string;
  summary: string;
  target_group_ids: string[];
  suggestions: string[];
  original_plan_id: string;
  new_plan_id: string;
}

export interface PlanReplans {
  items: ReplanItem[];
}

export interface PlanEvent {
  event_type: string;
  created_at?: string;
  payload: any;
  [key: string]: any;
}

export interface PlanDetail {
  plan_id: string;
  created_at: string | null;
  status: string;
  original_prompt: string;
  planner_reasoning: string;
  mode: string;
  metrics: PlanMetrics;
  tasks: PlanTaskSummary[];
  modules?: PlanModuleSummary[];
  qa_outcomes: QAOutcome[];
  security_outcome: SecurityOutcome | Record<string, never>;
  replans: PlanReplans;
  events: PlanEvent[];
}

