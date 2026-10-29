export const TASK_DOMAINS: Record<string, string> = {
  "language-model-analysis": "model-interpretability",
  "collaboration-analysis": "multi-agent-systems",
  "code-alignment": "code-generation",
  "retrieval-augmented-generation": "information-retrieval",
  "multimodal-alignment": "multimodal",
  "preference-optimization": "preference-optimization",
  "time-series-foundation": "time-series",
  "scientific-ml": "scientific-ml",
  "speech-representation": "speech",
};

export const RESEARCH_LINES = Object.keys(TASK_DOMAINS);

export const GLOBAL_SCOPE_TASKS = new Set(["", "general", "research", "all"]);

export function domainForTask(task: string): string {
  return TASK_DOMAINS[task.trim()] ?? "";
}

export function isGlobalScope(task: string, domain: string): boolean {
  return GLOBAL_SCOPE_TASKS.has(task.trim()) && GLOBAL_SCOPE_TASKS.has(domain.trim());
}
