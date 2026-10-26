export interface ImportDocument {
  id: string;
  text: string;
  embedding: number[];
  metadata: Record<string, string | number>;
}

export interface SearchHit {
  id: string;
  text: string;
  metadata: Record<string, unknown>;
  distance: number | null;
}

export interface SearchResponse {
  ms: number;
  hits: SearchHit[];
}

export interface ImportResponse {
  collection: string;
  written: number;
  ms: number;
  refreshMs: number | null;
  refreshError?: string | null;
  total: number;
}

export interface StatsResponse {
  collection: string;
  total: number;
  dimension: number;
  analyzer: string;
  /** True when the collection was created on this connection and has rows. */
  ready: boolean;
}

export interface CorpusFile {
  name: string;
  text: string;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${path} failed: ${response.status} ${detail.slice(0, 200)}`);
  }
  return (await response.json()) as T;
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`${path} failed: ${response.status} ${(await response.text()).slice(0, 200)}`);
  }
  return (await response.json()) as T;
}

/**
 * Passing `refresh: false` lets the page stream a large import in several requests
 * without rebuilding the index after every batch; one `refreshIndex` at the end makes
 * the whole import searchable.
 */
export function importDocuments(documents: ImportDocument[], collection: string, options: { refresh?: boolean } = {}) {
  return post<ImportResponse>("/api/import", {
    documents,
    collection,
    refresh: options.refresh !== false,
  });
}

export function refreshIndex(collection: string) {
  return post<{ collection: string; ms: number; total: number }>("/api/refresh", { collection });
}

export function search(
  query: string,
  embedding: number[] | null,
  k: number,
  collection: string,
  mode: "hybrid" | "vector" | "fulltext" = "hybrid",
) {
  return post<SearchResponse & { collection: string; mode: string }>("/api/search", {
    query,
    embedding,
    k,
    collection,
    mode,
  });
}

export function reset(collection: string) {
  return post<{ ok: boolean; collection: string }>("/api/reset", { collection });
}

export function stats(collection: string) {
  return get<StatsResponse>(`/api/stats?collection=${encodeURIComponent(collection)}`);
}

export function corpus() {
  return get<{ files: CorpusFile[] }>("/api/corpus");
}

export function health(collection?: string) {
  const suffix = collection ? `?collection=${encodeURIComponent(collection)}` : "";
  return get<Record<string, unknown>>(`/api/health${suffix}`);
}