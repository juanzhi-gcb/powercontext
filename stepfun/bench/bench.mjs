/**
 * Quantisation quality comparison.
 *
 * Drives a real browser over the running app, then uses the page's own Embedder to encode
 * the same corpus and labelled queries under two precisions. Ranks come from cosine
 * similarity over the returned vectors, so both precisions go through identical code.
 *
 * Requires: npm i -D puppeteer-core, the app running (npm start), and a Chrome/Edge binary
 * path in CHROME_PATH (defaults to common Windows locations).
 */
import puppeteer from "puppeteer-core";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const corpusDir = path.resolve(here, "..", "data", "corpus");
const URL = process.env.KB_URL ?? "http://localhost:8787";
const BROWSER =
  process.env.CHROME_PATH ??
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";

const CORPUS_FILES = [
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
];

const docs = CORPUS_FILES.map((name) =>
  fs.readFileSync(path.join(corpusDir, name), "utf8").replace(/\s+/g, " ").trim(),
);

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

  const result = await page.evaluate(async ({ docs, queries }) => {
    const { Embedder } = window.__kb;

    const rank = (docVectors, queryVectors, targets) =>
      queryVectors.map((query, index) => {
        const scored = docVectors.map((doc, docIndex) => ({
          docIndex,
          score: doc.reduce((sum, value, position) => sum + value * query[position], 0),
        }));
        scored.sort((left, right) => right.score - left.score);
        return scored.findIndex((entry) => entry.docIndex === targets[index]) + 1;
      });

    const run = async (dtype) => {
      const embedder = new Embedder();
      const loadStart = performance.now();
      const backend = await embedder.load(dtype);
      const loadMs = performance.now() - loadStart;

      const docStart = performance.now();
      const docVectors = await embedder.embed(docs, 16);
      const docMs = performance.now() - docStart;

      const queryStart = performance.now();
      const queryVectors = await embedder.embed(queries.map((query) => query.text), 1);
      const queryMs = performance.now() - queryStart;

      const ranks = rank(docVectors, queryVectors, queries.map((query) => query.target));
      return {
        dtype,
        backend,
        loadMs: Math.round(loadMs),
        docMs: Math.round(docMs),
        queryMs: Math.round(queryMs),
        ranks,
        mrr: ranks.reduce((sum, value) => sum + 1 / value, 0) / ranks.length,
      };
    };

    return { q8: await run("q8"), fp32: await run("fp32") };
  }, { docs, queries });

  for (const run of [result.q8, result.fp32]) {
    console.log(
      `${run.dtype.toUpperCase()} (${run.backend}): load ${run.loadMs}ms | docs ${run.docMs}ms | queries ${run.queryMs}ms`,
    );
    console.log(`  ranks ${run.ranks.join(", ")} | MRR ${run.mrr.toFixed(3)}`);
  }
} finally {
  await browser.close();
}