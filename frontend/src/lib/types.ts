export type UserRef = { id: number; full_name: string; email: string; title: string } | null;

export type Me = {
  id: number;
  email: string;
  full_name: string;
  title: string;
  team: string;
  role: { key: string; name: string; description: string; permissions: string[] };
  last_login_at: string | null;
};

export type UserListItem = {
  id: number;
  full_name: string;
  email: string;
  title: string;
  team: string;
  role: string;
  role_key: string;
  can_approve_risk: boolean;
  last_login_at: string | null;
};

export type Page<T> = { items: T[]; total: number; page: number; page_size: number };

export type ControlStatus = "Effective" | "Ineffective" | "Needs Review" | "Not Assessed";
export type Severity = "Critical" | "High" | "Medium" | "Low";

export type Finding = {
  id: number;
  ref: string;
  title: string;
  description: string;
  control_id: string;
  control_name: string;
  control_domain: string;
  asset_id: string;
  asset_name: string;
  service_id: string | null;
  service_name: string | null;
  severity: Severity;
  risk_score: number;
  status: string;
  assigned_owner: UserRef;
  detected_at: string;
  last_seen_at: string;
  due_date: string;
  resolved_at: string | null;
  updated_at: string;
  age_days: number;
  overdue: boolean;
};

export type Assessment = {
  id: number;
  ref: string;
  run_id: number;
  run_ref: string;
  control_id: string;
  control_name: string;
  asset_id: string | null;
  asset_name: string | null;
  scope_identifier: string;
  assessed_at: string;
  recorded_at: string;
  result: ControlStatus;
  rule_key: string;
  rule_version: string;
  explanation: string;
  input_hash: string;
  finding_id: number | null;
  finding_ref: string | null;
  evidence_refs: string[];
};

export type Evidence = {
  id: number;
  ref: string;
  evidence_category: string;
  file_format: string;
  source: string;
  description: string;
  collected_at: string;
  uploaded_at: string;
  uploaded_by: string | null;
  asset_id: string | null;
  control_id: string | null;
  sha256: string;
  validation_status: "Valid" | "Invalid" | "Unstructured";
  validation_errors: string[];
  original_filename: string;
  size_bytes: number;
  payload?: unknown;
};

export type ScoreFactor = {
  key: string;
  label: string;
  weight: number;
  value: number;
  contribution: number;
  max_contribution: number;
  rationale: string;
  inputs: Record<string, unknown>;
};

export type ScoreBreakdown = {
  methodology_version: string;
  score: number;
  severity: Severity;
  weights: Record<string, number>;
  bands: Record<string, number>;
  factors: ScoreFactor[];
  disclaimer: string;
};

export type ServiceRef = { id: string; name: string; tier: string };

export type Exposure = { index: number; level: string; formula: string; inputs: number[] };

export type Kpis = {
  total_control_instances: number;
  control_definitions: number;
  control_definitions_failing: number;
  effective_controls: number;
  failed_controls: number;
  needs_review_controls: number;
  not_assessed_controls: number;
  effectiveness_rate: number;
  unresolved_findings: number;
  critical_findings: number;
  risk_accepted_findings: number;
  overdue_findings: number;
  open_remediation_actions: number;
  overdue_remediation_actions: number;
  services_at_risk: number;
  services_total: number;
};

export type ServiceAtRisk = {
  service_id: string;
  name: string;
  tier: string;
  unresolved_findings: number;
  critical_findings: number;
  exposure_index: number;
  exposure_level: string;
  exposure_formula: string;
  top_finding: { id: number; ref: string; title: string; risk_score: number } | null;
};

export type DashboardSummary = {
  kpis: Kpis;
  severity_distribution: { severity: Severity; count: number }[];
  domain_distribution: ({ domain: string; total: number } & Record<Severity, number>)[];
  services_at_risk: ServiceAtRisk[];
  critical_attention: Finding[];
  last_assessment: { id: number; ref: string; evaluated_at: string; trigger: string; triggered_by: string } | null;
};

export type TrendPoint = {
  run_id: number;
  evaluated_at: string;
  effective: number;
  ineffective: number;
  needs_review: number;
  effectiveness_rate: number;
};

export type ControlItem = {
  id: string;
  name: string;
  description: string;
  domain: string;
  objective: string;
  risk_addressed: string;
  owner: UserRef;
  frequency: string;
  rule_key: string;
  rule_parameters: Record<string, unknown>;
  evaluation_rule: string;
  evidence_category: string;
  required_evidence: string;
  failure_severity: Severity;
  current_status: ControlStatus;
  last_assessed_at: string | null;
  next_assessment_at: string | null;
  scope_count?: number;
  status_counts?: Partial<Record<ControlStatus, number>>;
  open_findings?: number;
  rule_version?: string;
};

export type Asset = {
  id: string;
  name: string;
  asset_type: string;
  description: string;
  business_owner: string;
  technical_owner: string;
  environment: string;
  criticality: Severity;
  internet_exposed: boolean;
  privileged_access_hub: boolean;
  has_redundancy: boolean;
  platform: string;
  lifecycle_status: string;
  last_assessed_at: string | null;
  updated_at: string;
  services?: string[];
  open_findings?: number;
};

export type Meta = {
  asset_types: string[];
  environments: string[];
  criticality: string[];
  lifecycle: string[];
  control_domains: string[];
  finding_statuses: string[];
  severities: string[];
  risk_categories: string[];
  treatments: string[];
  risk_ratings: string[];
  risk_statuses: string[];
  services: ServiceRef[];
  controls: { id: string; name: string; evidence_category: string }[];
};

export type Run = {
  id: number;
  ref: string;
  trigger: string;
  scope_description: string;
  evaluated_at: string;
  started_at: string;
  completed_at: string | null;
  status: string;
  triggered_by: string;
  summary: {
    results: Record<ControlStatus, number>;
    duration_ms: number;
    status_changes: { control_id: string; asset_id: string; from: string; to: string }[];
    findings_created: string[];
    findings_updated: number;
    findings_resolved: string[];
    findings_reopened: string[];
    findings_pending_validation: string[];
    scopes_evaluated: number;
    controls_evaluated: number;
  };
};

export type Citation = { type: string; id: string; label: string };

export type IntelAnswer = {
  question: string;
  intent: string;
  mode: "rule_based" | "ai";
  mode_label: string;
  answer: string;
  facts: string[];
  recommendations: string[];
  citations: Citation[];
  records_used: number;
  generated_at: string;
  notice: string | null;
  model: string | null;
};
