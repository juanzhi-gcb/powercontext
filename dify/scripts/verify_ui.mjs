// Real browser acceptance for the custom frontend.
//
//   npm install playwright-core
//   node scripts/verify_ui.mjs --base http://localhost:18081/ --out docs/evidence
//
// Uses the locally installed Microsoft Edge by default (no browser download).
// The script drives one full round through the BFF and the real Dify model,
// then claims the same 当票 from a second, clean browser context. It saves
// screenshots and exits non-zero on the first broken assertion.
import { chromium } from 'playwright-core';
import path from 'node:path';
import fs from 'node:fs';

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(`--${name}`);
  return index >= 0 && args[index + 1] ? args[index + 1] : fallback;
};

const BASE = option('base', 'http://localhost:18081/');
const OUT = option('out', 'docs/evidence');
const EDGE = option('edge', process.env.EDGE_PATH
  || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe');

fs.mkdirSync(OUT, { recursive: true });

function check(condition, message) {
  if (!condition) throw new Error(message);
}

async function waitLabel(page, text, timeout = 240000) {
  await page.waitForFunction(
    (expected) => (document.querySelector('#footStamp')?.textContent || '').includes(expected),
    text,
    { timeout },
  );
  await page.waitForTimeout(900);
}

const browser = await chromium.launch({ executablePath: EDGE, headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' });
  const page = await context.newPage();
  const errors = [];
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', (error) => errors.push(String(error)));

  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => document.querySelector('#ticketMini')?.textContent !== '—', { timeout: 20000 });
  const ticket = await page.textContent('#ticketMini');
  await page.screenshot({ path: path.join(OUT, 'ui-home.png') });

  const say = async (text) => {
    await page.fill('#query', text);
    await page.click('#send');
  };

  await say('我总拿自己和同龄人比较，看到别人的消息就不舒服。');
  await waitLabel(page, '鉴定完成');
  const speech = await page.textContent('#speech');
  check(!speech.includes('外观：'), 'reply and card fields were not separated');
  check(await page.isVisible('#itemCard'), 'item card did not appear');
  check(await page.$eval('#itemCard', (element) => getComputedStyle(element).opacity) === '1',
    'item card is still animating');
  await page.screenshot({ path: path.join(OUT, 'ui-appraise.png') });

  await say('你鉴定错了，我不是嫉妒他们，我是觉得自己的努力一直没被看见。');
  await waitLabel(page, '鉴定已纠正');
  await page.screenshot({ path: path.join(OUT, 'ui-correct.png') });

  await say('确认典当');
  await waitLabel(page, '已确认典当');
  const status = await page.textContent('#itemTicket');
  check(status.includes('已入柜'), 'pawn did not reach the counter display');
  await page.screenshot({ path: path.join(OUT, 'ui-pawn.png') });

  await page.click('#shelfBtn');
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(OUT, 'ui-shelf.png') });
  const shelfItems = await page.$$eval('.shelf-item h3', (nodes) => nodes.map((node) => node.textContent));
  check(shelfItems.length === 1, 'shelf does not show exactly one item');
  await page.click('.shelf-item');
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(OUT, 'ui-provenance.png') });
  const provenance = await page.textContent('#provenanceList');
  check(provenance.includes('已写入长期记忆'), 'provenance does not show synced memory');
  await page.click('[data-close="provenanceDrawer"]');

  await page.click('#ticketBtn');
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(OUT, 'ui-ticket.png') });
  const ticketCode = await page.textContent('#ticketCode');
  await page.click('[data-close="ticketModal"]');

  // A second, clean browser claims the same 当票 and must see the same shelf.
  const otherContext = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' });
  const other = await otherContext.newPage();
  await other.goto(BASE, { waitUntil: 'networkidle' });
  await other.waitForFunction(() => document.querySelector('#ticketMini')?.textContent !== '—', { timeout: 20000 });
  await other.click('#ticketBtn');
  await other.fill('#claimInput', ticketCode);
  await other.click('#claimForm button');
  await other.waitForFunction(() => document.querySelector('#shelfCount')?.textContent === '1', { timeout: 20000 });
  await other.waitForTimeout(800);
  await other.screenshot({ path: path.join(OUT, 'ui-claim.png') });

  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'zh-CN', isMobile: true });
  const phone = await mobile.newPage();
  await phone.goto(BASE, { waitUntil: 'networkidle' });
  await phone.waitForTimeout(2500);
  await phone.screenshot({ path: path.join(OUT, 'ui-mobile.png') });

  check(errors.length === 0, `browser console errors: ${errors.join(' | ')}`);
  console.log(JSON.stringify({
    result: 'passed', ticket, shelfItems, status,
    claimed: await other.textContent('#ticketMini'),
    screenshots: fs.readdirSync(OUT).filter((name) => name.startsWith('ui-')),
  }, null, 2));
} finally {
  await browser.close();
}