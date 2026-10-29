import corpusData from "./public-archive.json";
import embeddingData from "./public-archive-embeddings.json";
import { blake2b128 } from "./blake2b";
import { isGlobalScope } from "./domains";
import type {
  AttemptInput,
  CheckResult,
  Comparison,
  Decision,
  Evidence,
  HistoryResult,
  HistorySearchResponse,
  Report,
} from "./types";

const DIMENSIONS = 64;
const RRF_K = 60;
const VECTOR_WEIGHT = 0.6;
const FTS_WEIGHT = 0.4;
const HYBRID_LIMIT = 6;
const CHANNEL_LIMIT = 8;
const SEARCH_RESULT_LIMIT = 3;

export const PUBLIC_RETRIEVAL = "browser-vector-fts-rrf-v1";
export const PUBLIC_RULES = "research-ci-rules-v1";
export const PUBLIC_COMPARATOR = "deterministic-mechanism-v1";
export const PUBLIC_EMBEDDING = "hashing-char-word-64-v1";

interface ArchiveRecord {
  id: string;
  title: string;
  idea: string;
  mechanism: string;
  failure_condition: string;
  task: string;
  domain: string;
  assumptions: string[];
  search_terms: string[];
  historical_decision: Decision | null;
  available_at: string;
  evidence: Evidence[];
  record_type?: string;
  source?: string;
  source_url?: string;
  license?: string;
  retrieved_at?: string;
  original_doi?: string;
  replication_doi?: string;
  outcome?: string;
  outcome_quote?: string;
  discipline_raw?: string;
}

interface Candidate {
  id: string;
  title: string;
  idea: string;
  mechanism: string;
  failure_condition: string;
  task: string;
  domain: string;
  assumptions: string[];
}

interface Scored {
  record: ArchiveRecord;
  vector_distance: number | null;
  fts_score: number | null;
  vector_rank: number | null;
  fts_rank: number | null;
  fused_score: number;
}

const records = (corpusData as { records: ArchiveRecord[] }).records;
const docEmbeddings = embeddingData as Record<string, number[]>;

export interface PublicVerdict {
  id: string;
  title: string;
  task: string;
  domain: string;
  mechanism: string;
  failure_condition: string;
  available_at: string;
  decision: Decision;
  evidence: Evidence[];
}

export function listPublicVerdicts(): PublicVerdict[] {
  return records
    .filter((record) => record.historical_decision)
    .map((record) => ({
      id: record.id,
      title: record.title,
      task: record.task,
      domain: record.domain,
      mechanism: record.mechanism,
      failure_condition: record.failure_condition,
      available_at: record.available_at,
      decision: record.historical_decision as Decision,
      evidence: record.evidence,
    }))
    .sort((left, right) => Date.parse(right.available_at) - Date.parse(left.available_at));
}

export function publicArchiveStats() {
  return {
    records: records.length,
    withEvidence: records.filter((record) => record.evidence.length > 0).length,
    verdicts: records.filter((record) => record.historical_decision).length,
  };
}

const encoder = new TextEncoder();

function embed(text: string): number[] {
  const vector = new Array<number>(DIMENSIONS).fill(0);
  const normalized = text.toLowerCase().replace(/\s+/g, " ").trim();
  const words = normalized.match(/[a-z0-9_]+|[\u4e00-\u9fff]/g) ?? [];
  const features = new Set(words);
  for (let index = 0; index < Math.max(0, normalized.length - 2); index += 1) {
    features.add(normalized.slice(index, index + 3));
  }
  for (const feature of features) {
    const digest = blake2b128(encoder.encode(feature));
    let bucket = 0;
    for (let index = 0; index < 8; index += 1) {
      bucket = (bucket * 256 + digest[index]) % DIMENSIONS;
    }
    vector[bucket] += (digest[8] & 1) === 1 ? 1 : -1;
  }
  const norm = Math.sqrt(vector.reduce((sum, value) => sum + value * value, 0)) || 1;
  return vector.map((value) => Math.round((value / norm) * 1e8) / 1e8);
}

function distance(left: number[], right: number[]): number {
  let sum = 0;
  for (let index = 0; index < DIMENSIONS; index += 1) {
    const delta = left[index] - right[index];
    sum += delta * delta;
  }
  return Math.sqrt(sum);
}

const FTS_RELEVANCE_FLOOR = 0.25;

const FTS_STOPWORDS = new Set([
  "the", "and", "with", "from", "that", "this", "using", "into", "than", "for",
  "are", "was", "were", "has", "have", "had", "can", "not", "but", "its", "our",
  "under", "over", "after", "before", "when", "whether", "which", "may", "must",
  "does", "did", "how", "why", "what", "where", "who", "all", "any", "also",
  "two", "one", "three", "make", "made", "use", "used", "new", "many", "more",
  "most", "some", "such", "these", "those", "each", "other", "both", "only",
  "very", "much", "well", "then", "there", "their", "they", "you", "your", "we",
  "it", "as", "at", "by", "in", "of", "on", "or", "to", "is", "be", "do", "if",
  "so", "no", "up", "out", "about", "would", "could", "should", "will", "per",
  "via", "vs",
]);

function normalizeLatin(token: string): string {
  if (token.length > 4 && token.endsWith("ies")) return `${token.slice(0, -3)}y`;
  if (token.length > 5 && token.endsWith("es")) return token.slice(0, -2);
  if (token.length > 4 && token.endsWith("s") && !token.endsWith("ss")) return token.slice(0, -1);
  return token;
}

function ftsTokens(text: string): string[] {
  const lowered = text.toLowerCase();
  const tokens: string[] = [];
  for (const word of lowered.match(/[a-z0-9_]+/g) ?? []) {
    if (word.length <= 1 || FTS_STOPWORDS.has(word)) continue;
    tokens.push(normalizeLatin(word));
  }
  for (const run of lowered.match(/[\u4e00-\u9fff]+/g) ?? []) {
    if (run.length === 1) {
      tokens.push(run);
      continue;
    }
    for (let index = 0; index + 1 < run.length; index += 1) {
      tokens.push(run.slice(index, index + 2));
    }
  }
  return tokens;
}

function ftsText(
  record: Pick<ArchiveRecord, "title" | "idea" | "mechanism" | "failure_condition" | "search_terms">,
): string {
  return [record.title, record.idea, record.mechanism, record.failure_condition, ...record.search_terms].join(" ");
}

function embeddingText(text: { idea: string; mechanism: string; failure_condition: string; assumptions?: string[] }): string {
  return [text.idea, text.mechanism, text.failure_condition, ...(text.assumptions ?? [])].join(" ");
}

function documentFrequency(): Map<string, number> {
  const counts = new Map<string, number>();
  for (const record of records) {
    for (const token of new Set(ftsTokens(ftsText(record)))) {
      counts.set(token, (counts.get(token) ?? 0) + 1);
    }
  }
  return counts;
}

const df = documentFrequency();

function ftsScore(query: string, record: ArchiveRecord): number {
  const terms = new Set(ftsTokens(query));
  if (!terms.size) return 0;
  const counts = new Map<string, number>();
  for (const token of ftsTokens(ftsText(record))) {
    counts.set(token, (counts.get(token) ?? 0) + 1);
  }
  let score = 0;
  for (const term of terms) {
    const tf = counts.get(term) ?? 0;
    if (!tf) continue;
    const idf = Math.log(1 + records.length / (1 + (df.get(term) ?? 0)));
    score += (1 + Math.log(tf)) * idf;
  }
  return Math.round(score * 1e6) / 1e6;
}

function eligible(record: ArchiveRecord, candidate: Candidate, cutoff: string, matchAll: boolean): boolean {
  return (
    record.id !== candidate.id &&
    Date.parse(record.available_at) <= Date.parse(cutoff) &&
    (matchAll || record.task === candidate.task || record.domain === candidate.domain)
  );
}

function hybridRetrieve(
  candidate: Candidate,
  cutoff: string,
  queryEmbedding: number[],
  options: { evidenceOnly?: boolean; matchAll?: boolean } = {},
): Scored[] {
  const evidenceOnly = options.evidenceOnly ?? false;
  const matchAll = options.matchAll ?? false;
  const ftsRowsAll = records
    .filter((record) => eligible(record, candidate, cutoff, matchAll))
    .map((record) => ({ record, value: ftsScore(candidate.mechanism, record) }))
    .filter((row) => row.value > 0)
    .sort((left, right) => right.value - left.value);
  const topValue = ftsRowsAll[0]?.value ?? 0;
  const gated = evidenceOnly
    ? ftsRowsAll.filter((row) => evidenceAt(row.record, cutoff).length > 0)
    : ftsRowsAll;
  const relevant = topValue > 0
    ? gated.filter((row) => row.value >= topValue * FTS_RELEVANCE_FLOOR)
    : [];
  const pool = relevant.map((row) => row.record);
  const vectorRows = pool
    .map((record) => ({ record, value: distance(queryEmbedding, docEmbeddings[record.id]) }))
    .sort((left, right) => left.value - right.value)
    .slice(0, CHANNEL_LIMIT);
  const ftsRows = relevant.slice(0, CHANNEL_LIMIT);

  const merged = new Map<string, Scored>();
  for (const [channel, rows] of [["vector", vectorRows], ["fts", ftsRows]] as const) {
    const weight = channel === "vector" ? VECTOR_WEIGHT : FTS_WEIGHT;
    rows.forEach((row, index) => {
      const rank = index + 1;
      const item =
        merged.get(row.record.id) ??
        ({
          record: row.record,
          vector_distance: null,
          fts_score: null,
          vector_rank: null,
          fts_rank: null,
          fused_score: 0,
        } satisfies Scored);
      if (channel === "vector") {
        item.vector_distance = row.value;
        item.vector_rank = rank;
      } else {
        item.fts_score = row.value;
        item.fts_rank = rank;
      }
      item.fused_score += weight / (RRF_K + rank);
      merged.set(row.record.id, item);
    });
  }
  return [...merged.values()]
    .sort((left, right) => right.fused_score - left.fused_score)
    .slice(0, HYBRID_LIMIT);
}

function evidenceAt(record: ArchiveRecord, cutoff: string): Evidence[] {
  return record.evidence.filter((item) => Date.parse(item.published_at) <= Date.parse(cutoff));
}

export async function searchPublicArchive(query: string): Promise<HistorySearchResponse> {
  const cutoff = new Date().toISOString();
  const candidate: Candidate = {
    id: "public-history-search",
    title: query,
    idea: query,
    mechanism: query,
    failure_condition: "",
    task: "general",
    domain: "",
    assumptions: [],
  };
  const scored = hybridRetrieve(candidate, cutoff, embed(query), { evidenceOnly: true, matchAll: true });
  const results: HistoryResult[] = [];
  for (const item of scored) {
    const evidence = evidenceAt(item.record, cutoff);
    if (!evidence.length) continue;
    results.push({
      attempt_id: item.record.id,
      title: item.record.title,
      task: item.record.task,
      domain: item.record.domain,
      historical_decision: item.record.historical_decision ?? undefined,
      available_at: item.record.available_at,
      mechanism: item.record.mechanism,
      differentiator: "",
      vector_distance: item.vector_distance ?? undefined,
      fts_score: item.fts_score ?? undefined,
      fused_score: item.fused_score,
      evidence,
      record_type: item.record.record_type,
      source: item.record.source,
      source_url: item.record.source_url,
      outcome: item.record.outcome,
      outcome_quote: item.record.outcome_quote,
      original_doi: item.record.original_doi,
      replication_doi: item.record.replication_doi,
    });
    if (results.length === SEARCH_RESULT_LIMIT) break;
  }
  return { query, cutoff, results, retrieval: PUBLIC_RETRIEVAL };
}

const COMPARATOR_STOP = new Set(["the", "and", "with", "from", "that", "this", "using", "into", "than"]);

function comparatorTokens(text: string): Set<string> {
  return new Set(
    (text.toLowerCase().match(/[a-z0-9_]+|[\u4e00-\u9fff]/g) ?? []).filter(
      (token) => token.length > 1 && !COMPARATOR_STOP.has(token),
    ),
  );
}

function compare(
  candidate: { mechanism: string; differentiator: string },
  historical: ArchiveRecord,
  evidence: Evidence[],
): { similarity: number; difference: string; evidence_ids: string[] } {
  const candidateTokens = comparatorTokens(candidate.mechanism);
  const historicalTokens = comparatorTokens(historical.mechanism);
  const union = new Set([...candidateTokens, ...historicalTokens]);
  let overlap = 0;
  for (const token of candidateTokens) if (historicalTokens.has(token)) overlap += 1;
  const similarity = union.size ? overlap / union.size : 0;
  return {
    similarity: Math.round(similarity * 1e6) / 1e6,
    difference:
      candidate.differentiator.trim() ||
      "No changed causal condition was declared; the mechanisms must be treated as potentially equivalent.",
    evidence_ids: evidence.map((item) => item.id),
  };
}

function check(name: string, status: CheckResult["status"], reason: string, detail: string, refs: string[] = []): CheckResult {
  return { name, status, reason_code: reason, detail, evidence_ids: refs };
}

function constraints() {
  return { min_gpu_count: 2, max_pilot_hours: 48, min_storage_gb: 50, problem_before_baseline: true };
}

function quote(text: string, limit = 80): string {
  const value = text.trim().replace(/\s+/g, " ");
  if (value.length <= limit) return value;
  const cut = value.slice(0, limit);
  const punctuation = Math.max(cut.lastIndexOf("；"), cut.lastIndexOf(";"), cut.lastIndexOf("。"), cut.lastIndexOf("."), cut.lastIndexOf("，"), cut.lastIndexOf(","));
  const boundary = punctuation >= limit / 2 ? punctuation : Math.max(punctuation, cut.lastIndexOf(" "));
  return `${(boundary >= limit / 2 ? cut.slice(0, boundary) : cut).trimEnd()}…`;
}

function minimalExperiment(input: AttemptInput, top: Comparison | undefined) {
  const differentiator = quote(input.differentiator.trim().replace(/[。；;.\s]+$/u, ""));
  const competing = input.competing_explanations.map((item) => item.trim()).filter(Boolean);
  const failure = input.failure_condition.trim().replace(/[。；;.\s]+$/u, "");
  const target = input.task && input.task !== "general" ? `${input.task} 的任务分数` : "目标任务分数";
  const historical = top && top.evidence.length && top.mechanism_similarity >= 0.12 ? quote(top.title, 48) : "";
  const controlName = competing.length ? quote(competing[0], 48) : historical;

  const hypothesis = differentiator
    ? historical
      ? `如果「${differentiator}」成立，那么在「${historical}」的任务设置下复现时，结果应出现可测差异；若没有差异，就不能主张这条路线比它多提供了机制信息。`
      : `如果「${differentiator}」成立，最小实验应在「条件未改变」和「条件已改变」两组之间产生可测差异。`
    : historical
      ? `尚未声明差异：先写清与「${historical}」相比改变了哪个因果条件；没有这句话，假设不可检验。`
      : "尚未声明差异：先写清改变了哪个因果条件；没有这句话，假设不可检验。";

  const intervention = differentiator
    ? historical
      ? `只改「${differentiator}」；数据、模型版本、预算和评测保持固定，并以「${historical}」为参照。`
      : `只改「${differentiator}」；其余条件全部固定。`
    : "待补：写出唯一改变的变量；没有它就没有可执行的干预。";

  const control = competing.length
    ? `用「${quote(competing[0], 48)}」在相同数据和预算下跑同一套评测；如果它也能解释结果，新机制不成立。`
    : historical
      ? `先复现「${historical}」的做法作为控制；它是当前最接近、且有可定位证据的历史记录。`
      : "待补：写下至少一个能解释同一结果的简单替代方案。";

  const metric = differentiator
    ? `机制指标：同一测量流程在「条件未改变」和「条件已改变」两组上的读数差，直接对应「${differentiator}」；任务指标：${target}。开跑前写死两者的计算方式。`
    : "待补：先确定用什么数值判断新条件成立；没有可测指标就无法预注册。";

  const threshold = controlName
    ? `在 ${input.pilot_hours}h、${input.gpu_count} 块 GPU 内，让「${controlName}」也跑同一套评测；机制指标的差值必须大于它重复运行的波动（默认重复 2 次，开跑前可改）。`
    : "待补：先确定控制组，才能设通过阈值。";

  const stop_condition = `${failure || "机制指标没有分离"}；首轮超过 ${input.pilot_hours}h 也停止。`;

  return { hypothesis, intervention, control, metric, threshold, stop_condition };
}

async function snapshot(cutoff: string) {
  const attempts = records
    .filter((record) => Date.parse(record.available_at) <= Date.parse(cutoff))
    .map((record) => [record.id, record.available_at])
    .sort((left, right) => (left[0] < right[0] ? -1 : 1));
  const evidence = records
    .flatMap((record) => record.evidence)
    .filter((item) => Date.parse(item.published_at) <= Date.parse(cutoff))
    .map((item) => [item.id, item.published_at])
    .sort((left, right) => (left[0] < right[0] ? -1 : 1));
  const canonical = JSON.stringify({ attempts, evidence });
  const digest = await crypto.subtle.digest("SHA-256", encoder.encode(canonical));
  const hash = [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return { hash, attempts: attempts.length, evidence: evidence.length };
}

export async function evaluatePublicAttempt(
  input: AttemptInput,
  options: { matchAll?: boolean } = {},
): Promise<Report> {
  const cutoff = new Date();
  if (Date.parse(input.available_at) > cutoff.getTime()) {
    throw new Error("这份提案的资料时间晚于当前预检时间，不能回放到过去。请把资料可用时间改到当前时间之前。");
  }
  const matchAll = options.matchAll ?? isGlobalScope(input.task, input.domain);
  const cutoffIso = cutoff.toISOString();
  const candidate: Candidate = {
    id: "public-candidate",
    title: input.title,
    idea: input.idea,
    mechanism: input.mechanism,
    failure_condition: input.failure_condition,
    task: input.task,
    domain: input.domain,
    assumptions: input.assumptions,
  };
  const scored = hybridRetrieve(candidate, cutoffIso, embed(embeddingText(candidate)), { evidenceOnly: true, matchAll });
  const evidenceByAttempt = new Map(scored.map((item) => [item.record.id, evidenceAt(item.record, cutoffIso)]));
  const comparisons: Comparison[] = scored.map((item) => {
    const evidence = evidenceByAttempt.get(item.record.id) ?? [];
    const result = compare(
      { mechanism: input.mechanism, differentiator: input.differentiator },
      item.record,
      evidence,
    );
    return {
      attempt_id: item.record.id,
      title: item.record.title,
      task: item.record.task,
      domain: item.record.domain,
      historical_decision: item.record.historical_decision ?? undefined,
      available_at: item.record.available_at,
      vector_distance: item.vector_distance ?? undefined,
      fts_score: item.fts_score ?? undefined,
      vector_rank: item.vector_rank ?? undefined,
      fts_rank: item.fts_rank ?? undefined,
      fused_score: item.fused_score,
      mechanism_similarity: result.similarity,
      mechanism_difference: result.difference,
      evidence_ids: result.evidence_ids,
      evidence,
      record_type: item.record.record_type,
      source: item.record.source,
      source_url: item.record.source_url,
      outcome: item.record.outcome,
    };
  });

  const limits = constraints();
  const attemptRef = `attempt:${candidate.id}#resources`;
  const baselineFailed = limits.problem_before_baseline && input.baseline_first;
  const checks: CheckResult[] = [
    check("engineering.data", input.data_ready ? "pass" : "fail", input.data_ready ? "DATA_READY" : "DATA_NOT_READY", "Minimum usable data must be available before mechanism work continues.", [attemptRef]),
    check("engineering.checkpoint", input.checkpoint_ready ? "pass" : "fail", input.checkpoint_ready ? "CHECKPOINT_READY" : "CHECKPOINT_MISSING", "The required model checkpoint must be available at the pinned revision.", [attemptRef]),
    check("engineering.gpu", input.gpu_count >= limits.min_gpu_count ? "pass" : "fail", input.gpu_count >= limits.min_gpu_count ? "GPU_BUDGET_OK" : "GPU_BUDGET_INSUFFICIENT", `Available GPUs: ${input.gpu_count}; required: ${limits.min_gpu_count}.`, [attemptRef]),
    check("engineering.closed_loop", input.pilot_hours <= limits.max_pilot_hours ? "pass" : "fail", input.pilot_hours <= limits.max_pilot_hours ? "PILOT_WITHIN_BUDGET" : "PILOT_EXCEEDS_BUDGET", `Pilot: ${input.pilot_hours}h; maximum: ${limits.max_pilot_hours}h.`, [attemptRef]),
    check("engineering.storage", input.storage_gb >= limits.min_storage_gb ? "pass" : "fail", input.storage_gb >= limits.min_storage_gb ? "STORAGE_BUDGET_OK" : "STORAGE_BUDGET_INSUFFICIENT", `Available storage: ${input.storage_gb}GB; required: ${limits.min_storage_gb}GB.`, [attemptRef]),
    check("process.problem_first", baselineFailed ? "fail" : "pass", baselineFailed ? "BASELINE_BEFORE_PROBLEM" : "PROBLEM_BEFORE_BASELINE", "A baseline must not be selected first and then reverse-packaged as a research question.", [attemptRef]),
  ];

  const coverageMissing = comparisons.slice(0, 3).some((item) => !item.evidence.length);
  checks.push(
    check(
      "evidence.coverage",
      !comparisons.length || coverageMissing ? "warn" : "pass",
      !comparisons.length || coverageMissing ? "EVIDENCE_MISSING" : "EVIDENCE_LOCATABLE",
      "Every key historical comparison needs at least one source locator available at the cutoff.",
      comparisons.slice(0, 3).flatMap((item) => item.evidence.map((evidence) => evidence.id)),
    ),
  );
  checks.push(
    check(
      "evidence.discrimination",
      input.competing_explanations.length ? "pass" : "warn",
      input.competing_explanations.length ? "COMPETING_EXPLANATION_DECLARED" : "COMPETING_EXPLANATION_MISSING",
      "The minimum experiment must distinguish the proposed mechanism from a trivial alternative.",
    ),
  );

  const top = comparisons[0];
  const repackaged = Boolean(
    top && top.mechanism_similarity >= 0.55 && !input.differentiator.trim(),
  );
  checks.push(
    check(
      "mechanism.repaint",
      repackaged ? "fail" : top ? "pass" : "unknown",
      repackaged ? "MECHANISM_REPACKAGED" : "CHANGED_CONDITION_DECLARED",
      top ? top.mechanism_difference : "No eligible historical mechanism was recalled.",
      top ? top.evidence_ids : [],
    ),
  );

  const engineeringFailed = checks.some((item) => item.name.startsWith("engineering.") && item.status === "fail");
  const evidenceIds = [...new Set(comparisons.slice(0, 3).flatMap((item) => item.evidence.map((evidence) => evidence.id)))];
  let machineDecision: Decision;
  let reasonCode: string;
  let summary: string;
  if (engineeringFailed || baselineFailed) {
    machineDecision = "NO_GO";
    reasonCode = "DETERMINISTIC_GATE_FAILED";
    summary = "A deterministic resource, closed-loop, or problem-first gate failed.";
  } else if (repackaged) {
    machineDecision = "NO_GO";
    reasonCode = "MECHANISM_REPACKAGED";
    summary = "The closest mechanism is highly similar and no changed causal condition was declared.";
  } else if (!top || !top.evidence.length) {
    machineDecision = "INSUFFICIENT_EVIDENCE";
    reasonCode = "NO_LOCATABLE_HISTORICAL_EVIDENCE";
    summary = "The system found insufficient cutoff-valid evidence for a substantiated decision.";
  } else if (top.mechanism_similarity >= 0.12 || top.fused_score > 0.01) {
    machineDecision = "CONDITIONAL_GO";
    reasonCode = "DIFFERENTIATED_MECHANISM";
    summary = "A changed condition is declared; proceed only through the minimum discriminating experiment.";
  } else {
    machineDecision = "INSUFFICIENT_EVIDENCE";
    reasonCode = "MECHANISM_RELATION_UNCERTAIN";
    summary = "Retrieval did not establish a reliable mechanism relation; add a more specific mechanism description or a closer comparison.";
  }

  const publicSnapshot = await snapshot(cutoffIso);
  return {
    id: `PUBLIC-${Date.now().toString(36).toUpperCase()}`,
    attempt_id: candidate.id,
    attempt: {
      title: input.title,
      idea: input.idea,
      mechanism: input.mechanism,
      differentiator: input.differentiator,
    },
    cutoff: cutoffIso,
    machine_decision: machineDecision,
    reason_code: reasonCode,
    summary,
    evidence_ids: evidenceIds,
    comparisons,
    checks,
    constraints: limits,
    minimal_experiment: minimalExperiment(input, top),
    context_refs: [],
    versions: {
      model: PUBLIC_COMPARATOR,
      embedding: PUBLIC_EMBEDDING,
      rules: PUBLIC_RULES,
      retrieval: PUBLIC_RETRIEVAL,
    },
    snapshot_hash: publicSnapshot.hash,
    snapshot: { hash: publicSnapshot.hash, attempts: publicSnapshot.attempts, evidence: publicSnapshot.evidence },
  };
}
