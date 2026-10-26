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

export function importDocuments(documents: ImportDocument[], collection: string) {
  return post<{ written: number; ms: number; collection: string }>("/api/import", { documents, collection });
}

export function search(query: string, embedding: number[], k: number, collection: string, mode = "hybrid") {
  return post<SearchResponse & { collection: string }>("/api/search", { query, embedding, k, collection, mode });
}

export function reset(collection: string) {
  return post<{ ok: boolean; collection: string }>("/api/reset", { collection });
}

export function health(collection?: string) {
  const suffix = collection ? `?collection=${encodeURIComponent(collection)}` : "";
  return fetch(`/api/health${suffix}`).then((response) => response.json());
}