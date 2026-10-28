/**
 * Browser-level acceptance check: exercises the same buttons a reviewer clicks.
 *
 *   1. model loads (WebGPU path) and the badge names the backend and precision
 *   2. "载入示例语料" vectorises, writes and refreshes the index
 *   3. a query returns ranked hits and each stage of the metrics table is filled
 *   4. the full-text mode answers without a query embedding
 *   5. opening the app with ?backend=wasm shows the downgrade banner and still searches
 *
 * Usage: npm start (in another terminal), then `node bench/e2e.mjs`.
 * Env: KB_URL, CHROME_PATH.
 */
import puppeteer from "puppeteer-core";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const KB_URL = process.env.KB_URL ?? "http://127.0.0.1:8787";
const BROWSER = process.env.CHROME_PATH ?? defaultBrowser();
const COLLECTION = `e2e_${Date.now()}`;
const EMPTY_COLLECTION = `${COLLECTION}_empty`;

function defaultBrowser() {
  const candidates = [
    process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, "Google/Chrome/Application/chrome.exe"),
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate)) ?? candidates[1];
}

const checks = [];
function check(name, passed, detail = "") {
  checks.push({ name, passed, detail });
  console.log(`${passed ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
}

const browser = await puppeteer.launch({
  executablePath: BROWSER,
  headless: "new",
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--enable-unsafe-webgpu"],
  protocolTimeout: 600_000,
});

try {
  const page = await browser.newPage();
  await page.evaluateOnNewDocument((name) => localStorage.setItem("seekdb-kb.collection", name), COLLECTION);
  await page.goto(KB_URL, { waitUntil: "domcontentloaded", timeout: 60_000 });
  await page.waitForFunction(() => !document.querySelector("#import").disabled, { timeout: 300_000 });

  const backend = await page.$eval("#backend", (element) => element.textContent);
  const dtype = await page.$eval("#dtype", (element) => element.textContent);
  check("模型加载并显示后端", backend.includes("WEBGPU"), `${backend} / ${dtype}`);

  await page.click("#sample");
  await page.waitForFunction(
    () => document.querySelector("#importStatus").textContent.includes("可立即检索"),
    { timeout: 300_000 },
  );
  const importStatus = await page.$eval("#importStatus", (element) => element.textContent);
  const statsLine = await page.$eval("#stats", (element) => element.textContent);
  check("内置语料导入 + 索引刷新", /已写入 60 段/.test(importStatus), importStatus);
  check("集合状态显示段数", /60 段/.test(statsLine), statsLine);

  const waitForSearch = (target) =>
    target.waitForFunction(
      () =>
        !document.querySelector("#search").disabled &&
        /返回 \d+ 条结果|检索失败/.test(document.querySelector("#searchStatus").textContent),
      { timeout: 120_000 },
    );

  await page.type("#query", "Which record references CODE-0021?");
  await page.click("#search");
  await waitForSearch(page);
  const hits = await page.$$eval("#results li .result-meta", (nodes) => nodes.map((node) => node.textContent));
  check("混合检索返回排序结果", hits.length > 0 && hits[0].includes("CODE-0021"), hits[0] ?? "no hits");

  const metrics = await page.$$eval("#metrics tbody tr", (rows) =>
    rows.map((row) => `${row.children[0].textContent}=${row.children[1].textContent}`),
  );
  check(
    "指标面板记录了各阶段耗时",
    metrics.every((row) => !row.endsWith("=—")),
    metrics.join(" | "),
  );

  await page.select("#mode", "fulltext");
  await page.click("#search");
  await waitForSearch(page);
  const fulltextStatus = await page.$eval("#searchStatus", (element) => element.textContent);
  check("全文模式无需查询向量即可检索", fulltextStatus.includes("fulltext"), fulltextStatus);

  const timed = await page.evaluate(async () => window.__kb.runQuery("Which record references CODE-0021?"));
  check(
    "端到端包含查询向量化、检索及结果渲染",
    timed.queryEmbedMs > 0 && timed.endToEndMs >= timed.queryEmbedMs + timed.response.ms && timed.response.hits.length > 0,
    `embed=${timed.queryEmbedMs.toFixed(1)}ms seekdb=${timed.response.ms}ms endToEnd=${timed.endToEndMs.toFixed(1)}ms`,
  );

  await page.click("#sample");
  await page.waitForFunction(() => !document.querySelector("#sample").disabled, { timeout: 300_000 });
  const repeatedStats = await page.$eval("#stats", (element) => element.textContent);
  const repeatedImportStatus = await page.$eval("#importStatus", (element) => element.textContent);
  check("重复导入幂等", /60 段/.test(repeatedStats) && /已写入 60 段/.test(repeatedImportStatus) && repeatedImportStatus.includes("可立即检索"), `${repeatedStats}; ${repeatedImportStatus}`);

  await page.evaluate(() => {
    const transfer = new DataTransfer();
    transfer.items.add(new File(["The acceptance-extra-token document describes incremental writes after index refresh."], "acceptance-extra.txt", { type: "text/plain" }));
    document.querySelector("#files").files = transfer.files;
  });
  await page.click("#import");
  await page.waitForFunction(() => !document.querySelector("#import").disabled, { timeout: 300_000 });
  const incrementedStats = await page.$eval("#stats", (element) => element.textContent);
  const incrementalImportStatus = await page.$eval("#importStatus", (element) => element.textContent);
  await page.select("#mode", "vector");
  await page.$eval("#query", (element) => { element.value = "The acceptance-extra-token document describes incremental writes after index refresh."; });
  await page.click("#search");
  await waitForSearch(page);
  const incrementalHits = await page.$$eval("#results li .result-meta", (nodes) => nodes.map((node) => node.textContent));
  check("新增文件写入后可向量检索", /61 段/.test(incrementedStats) && incrementalImportStatus.includes("可立即检索") && incrementalHits.some((hit) => hit.includes("acceptance-extra")), incrementedStats);
  await page.select("#mode", "hybrid");
  await page.$eval("#query", (element) => { element.value = "acceptance-extra-token"; });
  await page.click("#search");
  await waitForSearch(page);
  const incrementalHybridHits = await page.$$eval("#results li .result-meta", (nodes) => nodes.map((node) => node.textContent));
  check("新增文件写入后可混合检索", incrementalHybridHits.some((hit) => hit.includes("acceptance-extra")));

  await page.$eval("#collection", (element, name) => {
    element.value = name;
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }, EMPTY_COLLECTION);
  await page.waitForFunction((name) => document.querySelector("#stats").textContent.includes(`集合 ${name} · 0 段`), {}, EMPTY_COLLECTION);
  await page.click("#search");
  await waitForSearch(page);
  const emptyHits = await page.$$eval("#results li .result-meta", (nodes) => nodes.length);
  const emptyStatus = await page.$eval("#searchStatus", (element) => element.textContent);
  await page.$eval("#collection", (element, name) => {
    element.value = name;
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }, COLLECTION);
  await page.waitForFunction((name) => document.querySelector("#stats").textContent.includes(`集合 ${name} · 61 段`), {}, COLLECTION);
  check("集合切换隔离且恢复原集合状态", emptyHits === 0 && /返回 0 条结果/.test(emptyStatus), emptyStatus);

  const wasmPage = await browser.newPage();
  await wasmPage.evaluateOnNewDocument((name) => localStorage.setItem("seekdb-kb.collection", name), COLLECTION);
  await wasmPage.evaluateOnNewDocument(() => {
    Object.defineProperty(navigator, "gpu", { configurable: true, get: () => undefined });
  });
  await wasmPage.goto(KB_URL, { waitUntil: "domcontentloaded", timeout: 60_000 });
  await wasmPage.waitForFunction(() => !document.querySelector("#import").disabled, { timeout: 300_000 });
  const wasmBackend = await wasmPage.$eval("#backend", (element) => element.textContent);
  const bannerVisible = await wasmPage.$eval("#banner", (element) => !element.hidden && element.textContent.length > 0);
  const bannerText = await wasmPage.$eval("#banner", (element) => element.textContent);
  check("无 WebGPU 时降级到 WASM 并给出提示", wasmBackend.includes("WASM") && bannerVisible, bannerText);

  await wasmPage.type("#query", "Which distance metric does seekdb use by default?");
  await wasmPage.click("#search");
  await waitForSearch(wasmPage);
  const wasmHits = await wasmPage.$$eval("#results li .result-meta", (nodes) => nodes.map((node) => node.textContent));
  check("WASM 下检索仍可用", wasmHits.length > 0, wasmHits[0] ?? "no hits");
} finally {
  await browser.close();
}

const failed = checks.filter((entry) => !entry.passed);
const resultsDir = path.join(path.dirname(fileURLToPath(import.meta.url)), "results");
fs.mkdirSync(resultsDir, { recursive: true });
fs.writeFileSync(path.join(resultsDir, "e2e.json"), JSON.stringify({ generatedAt: new Date().toISOString(), url: KB_URL, collection: COLLECTION, checks }, null, 2));
console.log(`\n${checks.length - failed.length}/${checks.length} checks passed`);
process.exit(failed.length === 0 ? 0 : 1);
