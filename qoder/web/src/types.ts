export type Decision = "NO_GO" | "CONDITIONAL_GO" | "INSUFFICIENT_EVIDENCE" | "GO";

export interface Evidence {
  id: string;
  attempt_id?: string;
  source_type: string;
  title: string;
  locator: string;
  excerpt: string;
  stance: "supports" | "refutes" | "limits";
  published_at: string;
}

export interface Comparison {
  attempt_id: string;
  title: string;
  task: string;
  domain: string;
  historical_decision?: Decision;
  available_at: string;
  vector_distance?: number;
  fts_score?: number;
  vector_rank?: number;
  fts_rank?: number;
  fused_score: number;
  mechanism_similarity: number;
  mechanism_difference: string;
  evidence_ids: string[];
  evidence: Evidence[];
  record_type?: string;
  source?: string;
  source_url?: string;
  outcome?: string;
}

export interface CheckResult {
  name: string;
  status: "pass" | "fail" | "warn" | "unknown";
  reason_code: string;
  detail: string;
  evidence_ids: string[];
}

export interface Report {
  id: string;
  attempt_id: string;
  attempt: {
    title: string;
    idea: string;
    mechanism: string;
    differentiator: string;
  };
  cutoff: string;
  machine_decision: Decision;
  reason_code: string;
  summary: string;
  evidence_ids: string[];
  comparisons: Comparison[];
  checks: CheckResult[];
  constraints: Record<string, number | boolean>;
  minimal_experiment: {
    hypothesis: string;
    intervention: string;
    control: string;
    metric: string;
    threshold: string;
    stop_condition: string;
  };
  context_refs: ContextRef[];
  versions: Record<string, string>;
  snapshot_hash?: string;
  snapshot?: { hash: string; attempts: number; evidence: number };
  replay_of?: string;
  regression?: {
    passed: boolean;
    assertions: Record<string, boolean>;
    expected_decision: Decision;
    actual_decision: Decision;
    required_evidence_ids: string[];
    forbidden_evidence_ids: string[];
    leaked_evidence_ids: string[];
    note: string;
  };
}

export interface ContextRef {
  artifact_id: string;
  revision: number;
  kind: string;
  sha256: string;
}

export interface ContextEntry extends Omit<ContextRef, "sha256"> {
  text: string;
  sha256?: string;
}

export interface Health {
  seekdb: { status: string; version?: string; error?: string };
  powercontext: {
    status: string;
    scope_id?: string;
    message?: string;
    entries?: ContextEntry[];
    references?: ContextRef[];
  };
}

export interface HistoryResult {
  attempt_id: string;
  title: string;
  task: string;
  domain: string;
  historical_decision?: Decision;
  available_at: string;
  mechanism: string;
  differentiator: string;
  vector_distance?: number;
  fts_score?: number;
  fused_score: number;
  evidence: Evidence[];
  record_type?: string;
  source?: string;
  source_url?: string;
  outcome?: string;
  outcome_quote?: string;
  original_doi?: string;
  replication_doi?: string;
}

export interface HistorySearchResponse {
  query: string;
  cutoff: string;
  results: HistoryResult[];
  retrieval: string;
}

export interface ResearchSourceInput {
  title: string;
  content: string;
  locator: string;
  published_at: string;
  source_type: "paper" | "log" | "code_audit";
  task: string;
  domain: string;
}

export interface SourceRecord {
  attempt_id: string;
  title: string;
  task: string;
  domain: string;
  available_at: string;
  evidence_count: number;
  source_type: string;
  locator: string;
  published_at: string;
  imported_at: string;
}

export interface SourceImportResponse {
  documents: number;
  imported: number;
  skipped: number;
  attempts: Array<{ id: string; title: string }>;
}

export type SecretaryProposalKind = "knowledge_line" | "near_duplicate" | "orphan";
export type SecretaryReviewStatus = "proposed" | "accepted" | "rejected" | "snoozed";

export interface SecretarySourceRef {
  attempt_id: string;
  title: string;
  locator: string;
  locators: string[];
  published_at: string;
  source_type: string;
  evidence_ids: string[];
}

export interface SecretaryProposal {
  id: string;
  kind: SecretaryProposalKind;
  title: string;
  summary: string;
  next_action: string;
  source_ids: string[];
  evidence_ids: string[];
  sources: SecretarySourceRef[];
  confidence: number;
  status: SecretaryReviewStatus;
  review_note: string;
  reviewed_at: string | null;
}

export interface SecretaryReport {
  status: "ready" | "not_run";
  run_id: string | null;
  generated_at: string | null;
  source_count: number;
  new_source_ids: string[];
  new_source_count: number;
  accepted_count: number;
  proposals: SecretaryProposal[];
  workspace: ContextRef | null;
  context: ContextRef | null;
}

export interface AttemptInput {
  title: string;
  idea: string;
  mechanism: string;
  task: string;
  domain: string;
  failure_condition: string;
  assumptions: string[];
  competing_explanations: string[];
  differentiator: string;
  available_at: string;
  gpu_count: number;
  data_ready: boolean;
  checkpoint_ready: boolean;
  pilot_hours: number;
  storage_gb: number;
  baseline_first: boolean;
}

export type Page = "hall" | "sources" | "secretary" | "report" | "new" | "evidence" | "regression" | "context" | "project";
