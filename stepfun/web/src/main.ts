import { Embedder, MODEL_ID, MODEL_REVISION, type Backend, type RequestedDtype } from "./embedder";
import { corpus, importDocuments, refreshIndex, reset, search, stats, type ImportDocument, type SearchHit } from "./api";
import { measureQuery } from "./query-timing";

const CHUNK_WORDS = 180;
const CHUNK_OVERLAP = 30;
const EMBED_BATCH = 16;
const WRITE_BATCH = 64;
const STORAGE_KEY = "seekdb-kb.collection";
const METRIC_ROWS = [
  "模型加载（含预热）",
  "文档向量化",
  "写入 seekdb",
  "索引刷新",
  "查询向量化",
  "seekdb 检索（服务端计时）",
  "端到端（提交查询 → 结果渲染）",
];

const params = new URLSearchParams(location.search);
const forcedBackend = params.get("backend") === "wasm" || params.get("backend") === "webgpu"
  ? (params.get("backend") as Backend)
  : null;
const requestedDtype = (params.get("dtype") as RequestedDtype | null) ?? "auto";

const elements = {
  files: document.querySelector<HTMLInputElement>("#files")!,
  collection: document.querySelector<HTMLInputElement>("#collection")!,
  importButton: document.querySelector<HTMLButtonElement>("#import")!,
  sampleButton: document.querySelector<HTMLButtonElement>("#sample")!,
  refreshButton: document.querySelector<HTMLButtonElement>("#refresh")!,
  progress: document.querySelector<HTMLProgressElement>("#progress")!,
  importStatus: document.querySelector<HTMLParagraphElement>("#importStatus")!,
  query: document.querySelector<HTMLInputElement>("#query")!,
  mode: document.querySelector<HTMLSelectElement>("#mode")!,
  searchButton: document.querySelector<HTMLButtonElement>("#search")!,
  searchStatus: document.querySelector<HTMLParagraphElement>("#searchStatus")!,
  results: document.querySelector<HTMLOListElement>("#results")!,
  metricsBody: document.querySelector<HTMLTableSectionElement>("#metrics tbody")!,
  backend: document.querySelector<HTMLSpanElement>("#backend")!,
  model: document.querySelector<HTMLSpanElement>("#model")!,
  dtype: document.querySelector<HTMLSpanElement>("#dtype")!,
  resetButton: document.querySelector<HTMLButtonElement>("#reset")!,
  banner: document.querySelector<HTMLParagraphElement>("#banner")!,
  stats: document.querySelector<HTMLParagraphElement>("#stats")!,
};

function activeCollection(): string {
  const name = elements.collection.value.trim();
  return name === "" ? "documents" : name;
}

/** Stable per-chunk id: re-importing a file updates its chunks instead of adding duplicates. */
function documentId(source: string, index: number): string {
  const slug = source
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${slug}-chunk-${index}`;
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

interface SourceFile {
  name: string;
  content: string;
}

function splitFiles(files: SourceFile[]) {
  const items: { id: string; text: string; source: string; chunk: number }[] = [];
  for (const file of files) {
    chunk(file.content).forEach((text, index) => {
      items.push({ id: documentId(file.name, index), text, source: file.name, chunk: index });
    });
  }
  return items;
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

/** The UI and matrix use the same inference, seekdb request and result renderer. */
async function runQuery(
  query: string,
  model: Embedder = embedder,
  collection: string = activeCollection(),
  mode: "hybrid" | "vector" | "fulltext" = "hybrid",
  k = 5,
) {
  return measureQuery(
    mode === "fulltext" ? null : async () => (await model.embed([query], 1))[0],
    (vector) => search(query, vector, k, collection, mode),
    async (response) => {
      renderHits(response.hits);
      // Allow the updated results to pass a paint opportunity before stopping the timer.
      await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
    },
  );
}

async function refreshStats() {
  try {
    const current = await stats(activeCollection());
    elements.stats.textContent = `集合 ${current.collection} · ${current.total} 段 · ${current.dimension} 维 · 分词器 ${current.analyzer}`;
  } catch (error) {
    elements.stats.textContent = `集合状态不可读：${error instanceof Error ? error.message : String(error)}`;
  }
}

async function initialise() {
  elements.model.textContent = `模型：${MODEL_ID}`;
  elements.dtype.textContent = requestedDtype === "auto" ? "精度：自动选择" : `精度：${requestedDtype.toUpperCase()}`;
  try {
    const backend = await embedder.load(requestedDtype, { forceBackend: forcedBackend });
    elements.dtype.textContent = `精度：${embedder.dtype.toUpperCase()}`;
    elements.backend.textContent = `后端：${embedder.describe()}`;
    elements.backend.className = `badge ${backend === "webgpu" ? "badge--ok" : "badge--warn"}`;
    if (backend === "wasm") {
      elements.banner.hidden = false;
      elements.banner.textContent =
        `已降级到 WASM：${embedder.fallbackReason ?? "WebGPU 初始化失败"}。核心流程完整可用，向量化速度低于 WebGPU。`;
    }
    recordMetric(
      "模型加载（含预热）",
      `${embedder.loadMs.toFixed(0)} ms（${embedder.describe()}，预热 ${embedder.warmupMs.toFixed(0)} ms）`,
    );
    elements.importButton.disabled = false;
    elements.sampleButton.disabled = false;
    elements.refreshButton.disabled = false;
    elements.searchButton.disabled = false;
  } catch (error) {
    elements.backend.textContent = "后端：加载失败";
    elements.backend.className = "badge badge--warn";
    elements.importStatus.textContent = `模型加载失败：${error instanceof Error ? error.message : String(error)}`;
  }
  void refreshStats();
}

/**
 * Import in a stream: embed 16 chunks at a time and flush a write every 64, so a large
 * corpus never sits in memory as one array and the first write lands while later chunks
 * are still being vectorised. The index is refreshed once, at the end.
 */
async function runImport(items: { id: string; text: string; source: string; chunk: number }[]) {
  if (items.length === 0) {
    elements.importStatus.textContent = "没有可导入的文本。";
    return;
  }
  const collection = activeCollection();
  elements.progress.value = 0;
  let written = 0;
  let embedMs = 0;
  let writeMs = 0;
  let buffer: ImportDocument[] = [];

  const flush = async () => {
    if (buffer.length === 0) return;
    const response = await importDocuments(buffer, collection, { refresh: false });
    written += response.written;
    writeMs += response.ms;
    buffer = [];
    elements.importStatus.textContent = `已写入 ${written}/${items.length} 段…`;
  };

  for (let start = 0; start < items.length; start += EMBED_BATCH) {
    const slice = items.slice(start, start + EMBED_BATCH);
    const embedStart = performance.now();
    const vectors = await embedder.embed(slice.map((item) => item.text), EMBED_BATCH);
    embedMs += performance.now() - embedStart;
    slice.forEach((item, offset) => {
      buffer.push({
        id: item.id,
        text: item.text,
        embedding: vectors[offset],
        metadata: { source: item.source, chunk: item.chunk },
      });
    });
    if (buffer.length >= WRITE_BATCH) await flush();
    elements.progress.value = Math.round((Math.min(start + slice.length, items.length) / items.length) * 100);
  }
  await flush();

  const refreshStart = performance.now();
  const refreshed = await refreshIndex(collection);
  const refreshMs = performance.now() - refreshStart;

  recordMetric("文档向量化", `${embedMs.toFixed(0)} ms / ${items.length} 段（${(items.length / (embedMs / 1000)).toFixed(1)} 段/秒）`);
  recordMetric("写入 seekdb", `${writeMs.toFixed(0)} ms / ${written} 段`);
  recordMetric("索引刷新", `${refreshMs.toFixed(0)} ms · 集合共 ${refreshed.total} 段`);
  elements.importStatus.textContent =
    `已写入 ${written} 段，索引刷新完成（${refreshMs.toFixed(0)} ms），集合共 ${refreshed.total} 段，可立即检索。`;
  await refreshStats();
}

elements.importButton.addEventListener("click", async () => {
  const files = Array.from(elements.files.files ?? []);
  if (files.length === 0) {
    elements.importStatus.textContent = "请先选择 .txt 或 .md 文件，或点击“载入示例语料”。";
    return;
  }
  elements.importButton.disabled = true;
  elements.sampleButton.disabled = true;
  try {
    const sources: SourceFile[] = [];
    for (const file of files) sources.push({ name: file.name, content: await file.text() });
    const items = splitFiles(sources);
    elements.importStatus.textContent = `切分完成：${items.length} 段，开始本地向量化…`;
    await runImport(items);
  } catch (error) {
    elements.importStatus.textContent = `导入失败：${error instanceof Error ? error.message : String(error)}`;
  } finally {
    elements.importButton.disabled = false;
    elements.sampleButton.disabled = false;
  }
});

elements.sampleButton.addEventListener("click", async () => {
  elements.importButton.disabled = true;
  elements.sampleButton.disabled = true;
  try {
    const { files } = await corpus();
    const items = splitFiles(files.map((file) => ({ name: file.name, content: file.text })));
    elements.importStatus.textContent = `内置语料 ${files.length} 个文件，共 ${items.length} 段，开始本地向量化…`;
    await runImport(items);
  } catch (error) {
    elements.importStatus.textContent = `载入示例语料失败：${error instanceof Error ? error.message : String(error)}`;
  } finally {
    elements.importButton.disabled = false;
    elements.sampleButton.disabled = false;
  }
});

elements.searchButton.addEventListener("click", async () => {
  const query = elements.query.value.trim();
  if (query === "") return;
  const mode = elements.mode.value as "hybrid" | "vector" | "fulltext";
  elements.searchButton.disabled = true;
  try {
    const { response, queryEmbedMs, endToEndMs } = await runQuery(query, embedder, activeCollection(), mode);
    recordMetric("查询向量化", mode === "fulltext" ? "—（全文模式不向量化）" : `${queryEmbedMs.toFixed(0)} ms`);
    recordMetric("seekdb 检索（服务端计时）", `${response.ms.toFixed(0)} ms（${mode}）`);
    recordMetric("端到端（提交查询 → 结果渲染）", `${endToEndMs.toFixed(0)} ms`);
    elements.searchStatus.textContent =
      `返回 ${response.hits.length} 条结果（${mode}，后端 ${embedder.backend.toUpperCase()}）`;
  } catch (error) {
    elements.searchStatus.textContent = `检索失败：${error instanceof Error ? error.message : String(error)}`;
  } finally {
    elements.searchButton.disabled = false;
  }
});

elements.refreshButton.addEventListener("click", async () => {
  elements.refreshButton.disabled = true;
  try {
    const refreshed = await refreshIndex(activeCollection());
    recordMetric("索引刷新", `${refreshed.ms.toFixed(0)} ms · 集合共 ${refreshed.total} 段`);
    elements.importStatus.textContent = `索引已刷新，集合共 ${refreshed.total} 段。`;
    await refreshStats();
  } catch (error) {
    elements.importStatus.textContent = `刷新失败：${error instanceof Error ? error.message : String(error)}`;
  } finally {
    elements.refreshButton.disabled = false;
  }
});

elements.resetButton.addEventListener("click", async () => {
  await reset(activeCollection());
  elements.results.innerHTML = "";
  elements.importStatus.textContent = "知识库已清空。";
  metrics.clear();
  renderMetrics();
  await refreshStats();
});

elements.collection.addEventListener("change", () => {
  localStorage.setItem(STORAGE_KEY, activeCollection());
  elements.results.innerHTML = "";
  elements.searchStatus.textContent = "";
  void refreshStats();
});

const stored = localStorage.getItem(STORAGE_KEY);
if (stored) elements.collection.value = stored;

renderMetrics();
if (params.get("bench") === "1") {
  // The benchmark loads its own Embedder per configuration; the page must not race it with
  // a second model load.
  elements.backend.textContent = "后端：基准模式";
} else {
  void initialise();
}

// Exposed for the reproducible benchmark harness: it drives both precisions through the
// same code path the page uses, so the comparison does not need a second implementation.
(window as unknown as Record<string, unknown>).__kb = { Embedder, MODEL_ID, MODEL_REVISION, runQuery };
