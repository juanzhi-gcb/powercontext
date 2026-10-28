import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = fs.readFileSync(path.join(root, "TECH_NOTE.md"), "utf8");
const escape = (value) => value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
const inline = (value) => escape(value)
  .replace(/`([^`]+)`/g, "<code>$1</code>")
  .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
  .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
const blocks = [];
let table = false;
for (const line of source.split(/\r?\n/)) {
  if (line.startsWith("|")) {
    if (/^\|[\s:|\-]+\|$/.test(line)) continue;
    const first = !table;
    if (first) { blocks.push("<table>"); table = true; }
    const tag = first ? "th" : "td";
    blocks.push(`<tr>${line.slice(1, -1).split("|").map((cell) => `<${tag}>${inline(cell.trim())}</${tag}>`).join("")}</tr>`);
    continue;
  }
  if (table) { blocks.push("</table>"); table = false; }
  if (!line.trim()) continue;
  const heading = /^(#{1,3}) (.*)$/.exec(line);
  blocks.push(heading ? `<h${heading[1].length}>${inline(heading[2])}</h${heading[1].length}>` : `<p>${inline(line)}</p>`);
}
if (table) blocks.push("</table>");
const html = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>seekdb × 阶跃星辰 技术说明</title>
<style>
@page { size:A4; margin:13mm; }
body { font:9.5pt/1.48 "Microsoft YaHei","Noto Sans CJK SC",sans-serif; color:#17212c; margin:0; }
h1 { font-size:17pt; margin:0 0 8px; color:#073d4c; }
h2 { font-size:11pt; margin:10px 0 4px; color:#073d4c; border-bottom:1px solid #cedce0; padding-bottom:3px; }
p { margin:4px 0; }
code { font:8pt/1.4 Consolas,monospace; overflow-wrap:anywhere; }
table { border-collapse:collapse; width:100%; font-size:8.1pt; margin:7px 0; }
th,td { padding:5px 4px; border-bottom:1px solid #d6e0e5; text-align:left; vertical-align:top; }
th { background:#eaf2f4; } tr { break-inside:avoid; }
a { color:inherit; text-decoration:none; }
</style><body>${blocks.join("\n")}</body></html>`;
fs.writeFileSync(path.join(root, "TECH_NOTE.html"), html);
const browserPath = process.env.CHROME_PATH ?? [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  "/usr/bin/chromium", "/usr/bin/google-chrome",
].find((candidate) => fs.existsSync(candidate));
if (!browserPath) throw new Error("Set CHROME_PATH to a Chrome/Edge executable");
const browser = await puppeteer.launch({ executablePath: browserPath, headless: true, args: ["--no-sandbox"] });
try {
  const page = await browser.newPage();
  await page.setContent(html, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  await page.pdf({ path: path.join(root, "TECH_NOTE.pdf"), format: "A4", printBackground: true, preferCSSPageSize: true });
} finally {
  await browser.close();
}
console.log("Rendered TECH_NOTE.html and TECH_NOTE.pdf from TECH_NOTE.md");
