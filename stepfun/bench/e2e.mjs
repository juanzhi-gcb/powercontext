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

const KB_URL = process.env.KB_URL ?? "http://127.0.0.1:8787";
const BROWSER = process.env.CHROME_PATH ?? defaultBrowser();

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

  const wasmPage = await browser.newPage();
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
console.log(`\n${checks.length - failed.length}/${checks.length} checks passed`);
process.exit(failed.length === 0 ? 0 : 1);