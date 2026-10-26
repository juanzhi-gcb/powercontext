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

export function importDocuments(documents: ImportDocument[]) {
  return post<{ written: number; ms: number }>("/api/import", { documents });
}

export function search(query: string, embedding: number[], k: number) {
  return post<SearchResponse>("/api/search", { query, embedding, k });
}

export function reset() {
  return post<{ ok: boolean }>("/api/reset", {});
}

export function health() {
  return fetch("/api/health").then((response) => response.json());
}