import type { AttemptInput, Decision, Health, HistorySearchResponse, Report, ResearchSourceInput, SecretaryReport, SecretaryReviewStatus, SourceImportResponse, SourceRecord } from "./types";

const base = (import.meta.env.VITE_API_URL ?? "/api").replace(/\/$/, "");
export const staticDemo = import.meta.env.VITE_DEMO_MODE === "true";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    signal: init?.signal ?? AbortSignal.timeout(15000),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail));
  }
  return response.json();
}

export const api = {
  health: () => request<Health>("/health"),
  searchHistory: (query: string) =>
    request<HistorySearchResponse>("/history-search", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),
  createAttempt: (input: AttemptInput) =>
    request<{ id: string; context_warning?: string }>("/attempts", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  evaluate: (attemptId: string, cutoff: string) =>
    request<Report>("/evaluation-runs", {
      method: "POST",
      body: JSON.stringify({ attempt_id: attemptId, cutoff, use_context: true }),
    }),
  decide: (runId: string, decision: Decision, reason: string, restartConditions: string) =>
    request<{ id: string; context_warning?: string }>("/decisions", {
      method: "POST",
      body: JSON.stringify({
        run_id: runId,
        decision,
        reason,
        restart_conditions: restartConditions,
        reviewer_alias: "web-reviewer",
      }),
    }),
  replay: (sourceRunId: string, expectedDecision: Decision, required: string[], forbidden: string[]) =>
    request<Report>("/replays", {
      method: "POST",
      body: JSON.stringify({
        source_run_id: sourceRunId,
        expected_decision: expectedDecision,
        required_evidence_ids: required,
        forbidden_evidence_ids: forbidden,
      }),
    }),
  importSources: (sources: ResearchSourceInput[]) =>
    request<SourceImportResponse>("/imports/sources", {
      method: "POST",
      body: JSON.stringify({ sources }),
    }),
  listSources: () => request<SourceRecord[]>("/sources"),
  runSecretary: () =>
    request<SecretaryReport>("/secretary/runs", {
      method: "POST",
      body: JSON.stringify({}),
      signal: AbortSignal.timeout(120000),
    }),
  getSecretary: () => request<SecretaryReport>("/secretary"),
  reviewSecretary: (proposalId: string, status: SecretaryReviewStatus, note: string) =>
    request<SecretaryReport>("/secretary/reviews", {
      method: "POST",
      body: JSON.stringify({ proposal_id: proposalId, status, note }),
    }),
};
