import { chromium } from '@playwright/test';
const BASE = 'http://localhost:8088';
const OUT = process.argv[2];
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
page.on('pageerror', (e) => console.log('PAGEERROR', String(e).slice(0, 200)));
await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1800);
for (const [i, y] of [0, 130, 260, 390, 520].entries()) {
  await page.evaluate((v) => window.scrollTo(0, v), y);
  await page.waitForTimeout(900);
  await page.screenshot({ path: `${OUT}/h${i}-${y}.png`, clip: { x: 300, y: 0, width: 900, height: 100 } });
}
await page.goto(`${BASE}/events`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
await page.screenshot({ path: `${OUT}/z-events.png`, clip: { x: 300, y: 0, width: 900, height: 100 } });
await b.close();
console.log('done');
