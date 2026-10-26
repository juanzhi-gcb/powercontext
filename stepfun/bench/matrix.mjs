/**
 * The comparison the acceptance criteria ask for: one row per configuration, with model
 * size, embedding throughput, seekdb search latency, end-to-end query latency and retrieval
 * quality measured on the same corpus, the same labelled queries and the same machine.
 *
 * Every number comes from the app's own code path — the page's Embedder for inference and
 * the HTTP API for storage and search — so nothing here re-implements the pipeline.
 *
 * Usage:
 *   npm start                     # in another terminal
 *   npm run bench:matrix          # writes bench/results/matrix.json
 *
 * Env: KB_URL, CHROME_PATH, BENCH_REPEATS (default 3), BENCH_COLLECTION.
 */
import puppeteer from "puppeteer-core";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { CORPUS_FILES, QUERIES, gradeFor } from "./queries.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const corpusDir = path.resolve(here, "..", "data", "corpus");
const resultsDir = path.join(here, "results");
const KB_URL = process.env.KB_URL ?? "http://127.0.0.1:8787";
const REPEATS = Number(process.env.BENCH_REPEATS ?? 3);
const K = 5;
const COLLECTION = process.env.BENCH_COLLECTION ?? "bench";
const BROWSER = process.env.CHROME_PATH ?? defaultBrowser();

const CONFIGS = [
  { key: "fp32-webgpu", label: "量化前基线（FP32 + WebGPU）", dtype: "fp32", backend: "webgpu" },
  { key: "fp16-webgpu", label: "FP16 + WebGPU（应用默认）", dtype: "fp16", backend: "webgpu" },
  { key: "q8-webgpu", label: "INT8 + WebGPU（对照，非默认）", dtype: "q8", backend: "webgpu" },
  { key: "q8-wasm", label: "INT8 + WASM（降级默认）", dtype: "q8", backend: "wasm" },
];

const docs = CORPUS_FILES.map((name) =>
  fs.readFileSync(path.join(corpusDir, name), "utf8").replace(/\s+/g, " ").trim(),
);

function defaultBrowser() {
  const candidates = [
    process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, "Google/Chrome/Application/chrome.exe"),
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate)) ?? candidates[1];
}

const median = (values) => {
  if (values.length === 0) return null;
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};

function metrics(ranks) {
  let mrr = 0;
  let recall1 = 0;
  let recall5 = 0;
  let ndcg = 0;
  ranks.forEach((rankedFiles, queryIndex) => {
    const relevant = QUERIES[queryIndex].relevant;
    const position = rankedFiles.findIndex((file) => relevant.includes(file));
    if (position !== -1) mrr += 1 / (position + 1);
    if (position === 0) recall1 += 1;
    if (position !== -1 && position < K) recall5 += 1;
    let dcg = 0;
    rankedFiles.slice(0, K).forEach((file, index) => {
      const grade = gradeFor(relevant, file);
      if (grade > 0) dcg += (2 ** grade - 1) / Math.log2(index + 2);
    });
    const ideal = relevant
      .map((file) => gradeFor(relevant, file))
      .sort((left, right) => right - left)
      .slice(0, K);
    let idcg = 0;
    ideal.forEach((grade, index) => {
      idcg += (2 ** grade - 1) / Math.log2(index + 2);
    });
    ndcg += idcg === 0 ? 0 : dcg / idcg;
  });
  const count = ranks.length;
  return {
    mrr: mrr / count,
    recallAt1: recall1 / count,
    recallAt5: recall5 / count,
    ndcgAt5: ndcg / count,
  };
}

async function runConfig(config, modelInfo) {
  const browser = await puppeteer.launch({
    executablePath: BROWSER,
    headless: "new",
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--enable-unsafe-webgpu"],
    protocolTimeout: 1_800_000,
  });
  try {
    const page = await browser.newPage();
    if (config.backend === "wasm") {
      // Make the downgrade genuine: the page sees no WebGPU at all.
      await page.evaluateOnNewDocument(() => {
        Object.defineProperty(navigator, "gpu", { configurable: true, get: () => undefined });
      });
    }
    const url = `${KB_URL}/?bench=1&dtype=${config.dtype}&backend=${config.backend}`;
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await page.waitForFunction(() => Boolean(window.__kb), { timeout: 60_000 });

    const result = await page.evaluate(
      async ({ docs, corpusNames, queries, dtype, forceBackend, repeatCount, collection, k }) => {
        const { Embedder } = window.__kb;
        const post = async (path, body) => {
          const response = await fetch(path, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(body),
          });
          if (!response.ok) throw new Error(`${path}: ${response.status} ${await response.text()}`);
          return response.json();
        };

        const embedder = new Embedder();
        const backend = await embedder.load(dtype, { forceBackend });

        // Throughput: the whole corpus, repeated, median of the runs.
        const embedRuns = [];
        let vectors = null;
        for (let run = 0; run < repeatCount; run += 1) {
          const started = performance.now();
          vectors = await embedder.embed(docs, 16);
          embedRuns.push(performance.now() - started);
        }

        // Fresh collection per configuration, so vectors from one precision never mix with
        // another and the write timing is not dominated by existing rows.
        await post("/api/reset", { collection });
        let writeMs = 0;
        for (let start = 0; start < docs.length; start += 64) {
          const batch = docs.slice(start, start + 64);
          const response = await post("/api/import", {
            collection,
            refresh: false,
            documents: batch.map((text, offset) => ({
              id: `doc-${start + offset}`,
              text,
              embedding: vectors[start + offset],
              metadata: { source: corpusNames[start + offset] },
            })),
          });
          writeMs += response.ms;
        }
        const refreshed = await post("/api/refresh", { collection });

        const embedQuery = async (text) => {
          const started = performance.now();
          const [vector] = await embedder.embed([text], 1);
          return { vector, ms: performance.now() - started };
        };

        const first = await embedQuery(queries[0].text);
        const firstStart = performance.now();
        await post("/api/search", { collection, query: queries[0].text, embedding: first.vector, k, mode: "hybrid" });
        const firstQueryMs = performance.now() - firstStart;

        const queryEmbedMs = [];
        const searchMs = [];
        const endToEndMs = [];
        let ranks = [];
        for (let run = 0; run < repeatCount; run += 1) {
          const ranked = [];
          for (const query of queries) {
            const embedded = await embedQuery(query.text);
            const started = performance.now();
            const response = await post("/api/search", {
              collection,
              query: query.text,
              embedding: embedded.vector,
              k,
              mode: "hybrid",
            });
            const elapsed = performance.now() - started;
            queryEmbedMs.push(embedded.ms);
            searchMs.push(response.ms);
            endToEndMs.push(elapsed);
            ranked.push(response.hits.map((hit) => hit.metadata?.source ?? hit.id));
          }
          ranks = ranked; // every pass must return the same order; the last one is scored
        }

        return {
          backend,
          described: embedder.describe(),
          loadMs: embedder.loadMs,
          warmupMs: embedder.warmupMs,
          threads: embedder.threads,
          crossOriginIsolated: embedder.crossOriginIsolated,
          embedMedianMs: null,
          embedRuns,
          writeMs,
          refreshMs: refreshed.ms,
          total: refreshed.total,
          firstQueryMs,
          queryEmbedMs,
          searchMs,
          endToEndMs,
          ranks,
        };
      },
      {
        docs,
        corpusNames: CORPUS_FILES,
        queries: QUERIES.map((query) => ({ text: query.text })),
        dtype: config.dtype,
        forceBackend: config.backend,
        repeatCount: REPEATS,
        collection: COLLECTION,
        k: K,
      },
    );

    const quality = metrics(result.ranks);
    return {
      ...config,
      actualBackend: result.backend,
      described: result.described,
      threads: result.threads,
      crossOriginIsolated: result.crossOriginIsolated,
      modelBytes: modelInfo[config.dtype] ?? null,
      loadMs: Math.round(result.loadMs),
      warmupMs: Math.round(result.warmupMs),
      embedMs: Math.round(median(result.embedRuns)),
      embedRuns: result.embedRuns.map((ms) => Math.round(ms)),
      docsPerSecond: docs.length / (median(result.embedRuns) / 1000),
      msPerDoc: median(result.embedRuns) / docs.length,
      writeMs: Math.round(result.writeMs),
      refreshMs: Math.round(result.refreshMs),
      total: result.total,
      firstQueryMs: Math.round(result.firstQueryMs),
      queryEmbedMs: Math.round(median(result.queryEmbedMs)),
      searchMs: Math.round(median(result.searchMs)),
      endToEndMs: Math.round(median(result.endToEndMs)),
      quality,
      ranks: result.ranks.map((files, index) => files.indexOf(QUERIES[index].relevant[0])),
    };
  } finally {
    await browser.close();
  }
}

async function fetchModelInfo() {
  try {
    const response = await fetch(`${KB_URL}/api/model-info`);
    const body = await response.json();
    if (!body.local) return { fp32: null, q8: null, note: "weights not vendored (npm run models)" };
    const byName = Object.fromEntries(body.files.map((file) => [file.name, file.bytes]));
    return {
      fp32: byName["model.onnx"] ?? null,
      q8: byName["model_quantized.onnx"] ?? null,
      fp16: byName["model_fp16.onnx"] ?? null,
      note: "measured from public/models served by this app",
    };
  } catch {
    return { fp32: null, q8: null, note: "server not reachable" };
  }
}

const modelInfo = await fetchModelInfo();
const rows = [];
for (const config of CONFIGS) {
  process.stderr.write(`running ${config.label} …\n`);
  try {
    rows.push(await runConfig(config, modelInfo));
  } catch (error) {
    rows.push({ ...config, error: String(error?.message ?? error) });
  }
}

fs.mkdirSync(resultsDir, { recursive: true });
const output = {
  generatedAt: new Date().toISOString(),
  url: KB_URL,
  repeats: REPEATS,
  corpusChunks: docs.length,
  queries: QUERIES.length,
  model: modelInfo,
  rows,
};
fs.writeFileSync(path.join(resultsDir, "matrix.json"), JSON.stringify(output, null, 2));

const formatBytes = (bytes) => (bytes === null ? "—" : `${(bytes / 1e6).toFixed(2)} MB`);
const formatPct = (value) => `${(value * 100).toFixed(1)}%`;

console.log("\n| 配置 | 模型体积 | 向量化吞吐 | seekdb 检索延迟 | 端到端查询延迟 | MRR@5 | R@1 | R@5 | nDCG@5 |");
console.log("|---|---:|---:|---:|---:|---:|---:|---:|---:|");
for (const row of rows) {
  if (row.error) {
    console.log(`| ${row.label} | 失败：${row.error.slice(0, 60)} | — | — | — | — | — | — | — |`);
    continue;
  }
  console.log(
    `| ${row.label} | ${formatBytes(row.modelBytes)} | ${row.docsPerSecond.toFixed(1)} 段/秒 (${row.msPerDoc.toFixed(1)} ms/段) | ${row.searchMs} ms | ${row.endToEndMs} ms | ${row.quality.mrr.toFixed(3)} | ${formatPct(row.quality.recallAt1)} | ${formatPct(row.quality.recallAt5)} | ${row.quality.ndcgAt5.toFixed(3)} |`,
  );
}
console.log(`\nbackend actually used: ${rows.map((row) => `${row.key}=${row.actualBackend ?? "n/a"}`).join(", ")}`);
console.log(`model sizes: ${modelInfo.note}`);
console.log(`raw: ${path.relative(process.cwd(), path.join(resultsDir, "matrix.json"))}`);