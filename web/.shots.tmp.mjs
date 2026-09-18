import { chromium } from '@playwright/test';
const BASE = 'http://localhost:8088';
const OUT = process.argv[2];
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
page.on('pageerror', (e) => console.log('PAGEERROR', String(e).slice(0, 200)));
await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1600);
for (const [i, y] of [0, 160, 320, 440, 560].entries()) {
  await page.evaluate((v) => window.scrollTo(0, v), y);
  await page.waitForTimeout(850);
  await page.screenshot({ path: `${OUT}/h${i}-${y}.png`, clip: { x: 0, y: 0, width: 1440, height: 110 } });
}
await page.goto(`${BASE}/events`, { waitUntil: 'networkidle' });
await page.waitForTimeout(1000);
await page.screenshot({ path: `${OUT}/z-events-nav.png`, clip: { x: 0, y: 0, width: 1440, height: 110 } });
await b.close();
console.log('done');
