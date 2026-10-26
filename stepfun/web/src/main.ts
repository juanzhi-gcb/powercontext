import { Embedder, MODEL_ID } from "./embedder";
import { importDocuments, reset, search, type ImportDocument, type SearchHit } from "./api";

const CHUNK_WORDS = 180;
const CHUNK_OVERLAP = 30;
const BATCH_SIZE = 16;
const METRIC_ROWS = [
  "模型加载（含预热）",
  "文档向量化",
  "写入 seekdb",
  "查询向量化",
  "seekdb 混合检索（服务端计时）",
  "端到端（点击检索 → 结果渲染）",
];

const elements = {
  files: document.querySelector<HTMLInputElement>("#files")!,
  collection: document.querySelector<HTMLInputElement>("#collection")!,
  importButton: document.querySelector<HTMLButtonElement>("#import")!,
  progress: document.querySelector<HTMLProgressElement>("#progress")!,
  importStatus: document.querySelector<HTMLParagraphElement>("#importStatus")!,
  query: document.querySelector<HTMLInputElement>("#query")!,
  searchButton: document.querySelector<HTMLButtonElement>("#search")!,
  searchStatus: document.querySelector<HTMLParagraphElement>("#searchStatus")!,
  results: document.querySelector<HTMLOListElement>("#results")!,
  metricsBody: document.querySelector<HTMLTableSectionElement>("#metrics tbody")!,
  backend: document.querySelector<HTMLSpanElement>("#backend")!,
  model: document.querySelector<HTMLSpanElement>("#model")!,
  dtype: document.querySelector<HTMLSpanElement>("#dtype")!,
  resetButton: document.querySelector<HTMLButtonElement>("#reset")!,
};

function activeCollection(): string {
  const name = elements.collection.value.trim();
  return name === "" ? "documents" : name;
}

const metrics = new Map<string, string>();

function recordMetric(name: string, value: string) {
  metrics.set(name, value);
  renderMetrics();
}

function renderMetrics() {
  elements.metricsBody.innerHTML = "";
  for (const name of METRIC_ROWS) {
    const row = document.createElement("tr");
    const label = document.createElement("td");
    label.textContent = name;
    const value = document.createElement("td");
    value.textContent = metrics.get(name) ?? "—";
    row.append(label, value);
    elements.metricsBody.append(row);
  }
}

function chunk(text: string): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length <= CHUNK_WORDS) return [words.join(" ")];
  const chunks: string[] = [];
  for (let start = 0; start < words.length; start += CHUNK_WORDS - CHUNK_OVERLAP) {
    chunks.push(words.slice(start, start + CHUNK_WORDS).join(" "));
    if (start + CHUNK_WORDS >= words.length) break;
  }
  return chunks;
}

function renderHits(hits: SearchHit[]) {
  elements.results.innerHTML = "";
  for (const hit of hits) {
    const item = document.createElement("li");
    const meta = document.createElement("div");
    meta.className = "result-meta";
    const source = String(hit.metadata?.source ?? "unknown");
    const distance = hit.distance === null ? "—" : hit.distance.toFixed(4);
    meta.textContent = `${hit.id} · ${source} · distance ${distance}`;
    const body = document.createElement("div");
    body.className = "result-text";
    body.textContent = hit.text.length > 420 ? `${hit.text.slice(0, 420)}…` : hit.text;
    item.append(meta, body);
    elements.results.append(item);
  }
  if (hits.length === 0) {
    const item = document.createElement("li");
    item.textContent = "没有命中，先导入一些文档。";
    elements.results.append(item);
  }
}

const embedder = new Embedder();

async function initialise() {
  elements.model.textContent = `模型：${MODEL_ID}`;
  try {
    const backend = await embedder.load("q8");
    elements.backend.textContent = `后端：${backend.toUpperCase()}`;
    elements.backend.className = `badge ${backend === "webgpu" ? "badge--ok" : "badge--warn"}`;
    elements.dtype.textContent = "精度：INT8 (q8)";
    if (embedder.fallbackReason) {
      elements.backend.title = `WebGPU 不可用：${embedder.fallbackReason}`;
    }
    recordMetric("模型加载（含预热）", `${embedder.loadMs.toFixed(0)} ms（${backend}）`);
    elements.importButton.disabled = false;
    elements.searchButton.disabled = false;
  } catch (error) {
    elements.backend.textContent = "后端：加载失败";
    elements.backend.className = "badge badge--warn";
    elements.importStatus.textContent = `模型加载失败：${error instanceof Error ? error.message : String(error)}`;
  }
}

elements.importButton.addEventListener("click", async () => {
  const files = Array.from(elements.files.files ?? []);
  if (files.length === 0) {
    elements.importStatus.textContent = "请先选择 .txt 或 .md 文件。";
    return;
  }
  elements.importButton.disabled = true;
  elements.progress.value = 0;
  try {
    const texts: string[] = [];
    const sources: string[] = [];
    for (const file of files) {
      const content = await file.text();
      for (const part of chunk(content)) {
        texts.push(part);
        sources.push(file.name);
      }
    }
    elements.importStatus.textContent = `切分完成：${texts.length} 段，开始本地向量化…`;

    const started = performance.now();
    const vectors = await embedder.embed(texts, BATCH_SIZE, (done, total) => {
      elements.progress.value = Math.round((done / total) * 100);
      elements.importStatus.textContent = `向量化 ${done}/${total} 段…`;
    });
    const embedMs = performance.now() - started;
    recordMetric("文档向量化", `${embedMs.toFixed(0)} ms / ${vectors.length} 段`);

    const documents: ImportDocument[] = texts.map((text, index) => ({
      id: `doc-${index}`,
      text,
      embedding: vectors[index],
      metadata: { source: sources[index], chunk: index },
    }));
    const write = await importDocuments(documents, activeCollection());
    recordMetric("写入 seekdb", `${write.ms.toFixed(0)} ms / ${write.written} 段`);
    elements.importStatus.textContent = `已写入 ${write.written} 段，可以检索了。`;
  } catch (error) {
    elements.importStatus.textContent = `导入失败：${error instanceof Error ? error.message : String(error)}`;
  } finally {
    elements.importButton.disabled = false;
  }
});

elements.searchButton.addEventListener("click", async () => {
  const query = elements.query.value.trim();
  if (query === "") return;
  elements.searchButton.disabled = true;
  const endToEndStart = performance.now();
  try {
    const embedStart = performance.now();
    const [vector] = await embedder.embed([query], 1);
    const embedMs = performance.now() - embedStart;
    recordMetric("查询向量化", `${embedMs.toFixed(0)} ms`);

    const response = await search(query, vector, 5, activeCollection());
    recordMetric("seekdb 混合检索（服务端计时）", `${response.ms.toFixed(0)} ms`);
    renderHits(response.hits);
    recordMetric("端到端（点击检索 → 结果渲染）", `${(performance.now() - endToEndStart).toFixed(0)} ms`);
    elements.searchStatus.textContent = `返回 ${response.hits.length} 条结果（后端 ${embedder.backend.toUpperCase()}）`;
  } catch (error) {
    elements.searchStatus.textContent = `检索失败：${error instanceof Error ? error.message : String(error)}`;
  } finally {
    elements.searchButton.disabled = false;
  }
});

elements.resetButton.addEventListener("click", async () => {
  await reset(activeCollection());
  elements.results.innerHTML = "";
  elements.importStatus.textContent = "知识库已清空。";
  metrics.clear();
  renderMetrics();
});

renderMetrics();
void initialise();

// Exposed for the reproducible benchmark harness: it drives both precisions through the
// same code path the page uses, so the comparison does not need a second implementation.
(window as unknown as Record<string, unknown>).__kb = { Embedder, MODEL_ID };