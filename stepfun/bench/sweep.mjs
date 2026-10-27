/**
 * End-to-end sweep: embedding throughput by batch size, retrieval quality by search mode,
 * and how far the int8 vectors drift from the float baseline.
 *
 * Requires the app running (npm start) and puppeteer-core installed.
 *   CHROME_PATH=... node bench/sweep.mjs
 */
import puppeteer from "puppeteer-core";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const corpusDir = path.resolve(here, "..", "data", "corpus");
const URL = process.env.KB_URL ?? "http://localhost:8787";
const BROWSER = process.env.CHROME_PATH ?? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";

const CORPUS = [
  "01-vector-search.md",
  "02-hybrid-search.md",
  "03-mm39-embedding.md",
  "04-webgpu.md",
  "05-bm25.md",
  "06-index-refresh.md",
  "07-quantisation-tradeoff.md",
  "08-browser-inference.md",
];

const QUERIES = [
  { text: "How does seekdb fuse the two retrieval branches?", target: 1 },
  { text: "What happens when the browser has no WebGPU?", target: 3 },
  { text: "How much smaller is the int8 model?", target: 6 },
  { text: "Which distance metric does seekdb use by default?", target: 0 },
  { text: "Why is a document not searchable right after writing?", target: 5 },
  { text: "Which index structure trades recall for latency?", target: 0 },
  { text: "What does reciprocal rank fusion combine?", target: 1 },
  { text: "Which runtime executes the model when WebGPU is missing?", target: 3 },
];

const docs = CORPUS.map((name) =>
  fs.readFileSync(path.join(corpusDir, name), "utf8").replace(/\s+/g, " ").trim(),
);

const median = (values) => {
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};

const browser = await puppeteer.launch({
  executablePath: BROWSER,
  headless: "new",
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
  protocolTimeout: 1_800_000,
});

try {
  const page = await browser.newPage();
  await page.goto(URL, { waitUntil: "domcontentloaded", timeout: 60_000 });
  await page.waitForFunction(() => Boolean(window.__kb), { timeout: 60_000 });

  const result = await page.evaluate(async ({ docs, queries, corpusNames }) => {
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

    const positive = (vector) => vector.map((value) => Math.abs(value) + 1e-6);
    const cosine = (left, right) => {
      let dot = 0;
      let leftNorm = 0;
      let rightNorm = 0;
      for (let index = 0; index < left.length; index += 1) {
        dot += left[index] * right[index];
        leftNorm += left[index] * left[index];
        rightNorm += right[index] * right[index];
      }
      return dot / Math.sqrt(leftNorm * rightNorm);
    };

    const embedder = new Embedder();
    const backend = await embedder.load("q8");

    // Warm up, then measure throughput for one text repeated across the batch sizes.
    await embedder.embed([docs[0]], 1);
    const sample = docs[0];
    const batches = [1, 8, 16, 32];
    const throughput = [];
    for (const size of batches) {
      const runs = [];
      for (let repeat = 0; repeat < 5; repeat += 1) {
        const texts = Array.from({ length: size }, () => sample);
        const start = performance.now();
        await embedder.embed(texts, size);
        runs.push(performance.now() - start);
      }
      throughput.push({ size, medianMs: median(runs), perTextMs: median(runs) / size });
    }

    // Vectorise the corpus once per precision, and keep both for the drift comparison.
    const docQ8 = await embedder.embed(docs, 16);
    const queryVectors = await embedder.embed(queries.map((query) => query.text), 1);

    const float = new Embedder();
    await float.load("fp32");
    const docFloat = await float.embed(docs, 16);
    const drift = docQ8.map((vector, index) => cosine(positive(vector), positive(docFloat[index])));

    // Import through the real endpoint so the retrieval comparison uses seekdb.
    await post("/api/import", {
      documents: docQ8.map((embedding, index) => ({
        id: `doc-${index}`,
        text: docs[index],
        embedding,
        metadata: { source: corpusNames[index] },
      })),
    });

    const evaluateMode = async (mode) => {
      const ranks = [];
      const latencies = [];
      for (const query of queries) {
        const [vector] = await embedder.embed([query.text], 1);
        const started = performance.now();
        const response = await post("/api/search", { query: query.text, embedding: vector, k: 5, mode });
        latencies.push(performance.now() - started);
        const position = response.hits.findIndex((hit) => hit.id === `doc-${query.target}`);
        ranks.push(position === -1 ? 6 : position + 1);
      }
      return {
        mode,
        ranks,
        mrr: ranks.reduce((sum, rank) => sum + 1 / rank, 0) / ranks.length,
        top1: ranks.filter((rank) => rank === 1).length,
        medianLatencyMs: median(latencies),
      };
    };

    const hybrid = await evaluateMode("hybrid");
    const vectorOnly = await evaluateMode("vector");

    // First query vs warm query on the same path.
    const firstStart = performance.now();
    const [firstVector] = await embedder.embed([queries[0].text], 1);
    await post("/api/search", { query: queries[0].text, embedding: firstVector, k: 5, mode: "hybrid" });
    const firstQueryMs = performance.now() - firstStart;
    const warmStart = performance.now();
    const [warmVector] = await embedder.embed([queries[0].text], 1);
    await post("/api/search", { query: queries[0].text, embedding: warmVector, k: 5, mode: "hybrid" });
    const warmQueryMs = performance.now() - warmStart;

    return { backend, throughput, drift, hybrid, vectorOnly, firstQueryMs, warmQueryMs };
  }, { docs, queries, corpusNames: CORPUS });

  console.log("backend:", result.backend);
  console.log("\nembedding throughput (median of 5 runs)");
  for (const row of result.throughput) {
    console.log(`  batch ${String(row.size).padStart(2)}: ${row.medianMs.toFixed(0)} ms  (${row.perTextMs.toFixed(1)} ms/text)`);
  }
  console.log("\nint8 vs fp32 vector agreement (cosine, per document)");
  console.log(`  mean ${(result.drift.reduce((a, b) => a + b, 0) / result.drift.length).toFixed(5)} | min ${Math.min(...result.drift).toFixed(5)}`);
  console.log("\nretrieval quality by mode");
  for (const run of [result.hybrid, result.vectorOnly]) {
    console.log(`  ${run.mode.padEnd(7)} MRR ${run.mrr.toFixed(3)} | top1 ${run.top1}/${run.ranks.length} | median ${run.medianLatencyMs.toFixed(0)} ms`);
    console.log(`          ranks ${run.ranks.join(", ")}`);
  }
  console.log(`\nfirst query ${result.firstQueryMs.toFixed(0)} ms | warm query ${result.warmQueryMs.toFixed(0)} ms`);
} finally {
  await browser.close();
}