import { test, expect, type Page } from '@playwright/test';

/**
 * The landing page animates with Framer Motion (entrance variants) and GSAP
 * ScrollTrigger (the trail rows, the step band, the hero glow).
 *
 * The failure mode worth guarding is specific: both libraries work by setting an
 * element to `opacity: 0` and then animating it back. If a trigger never fires --
 * a refresh bug, a layout change, a reduced-motion path that skips the animation
 * but not the initial state -- the content is permanently invisible, the page
 * still "renders", and no existing test notices. These assert that nothing is
 * left stranded.
 */

/** Every element the page animates, by the hooks the implementation uses. */
const ANIMATED = '[data-role="step"], [data-role="accent-line"], section tr, section h2, section h3';

async function scrollThrough(page: Page) {
  // Walk the page so every ScrollTrigger gets a chance to fire, then come back.
  await page.evaluate(async () => {
    const step = window.innerHeight / 2;
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 40));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(900);
}

/** Elements that are visible in the layout but fully transparent. */
async function strandedCount(page: Page, selector: string): Promise<string[]> {
  return page.evaluate((sel) => {
    const stranded: string[] = [];
    for (const el of Array.from(document.querySelectorAll(sel))) {
      const box = (el as HTMLElement).getBoundingClientRect();
      if (box.width === 0 && box.height === 0) continue; // genuinely not laid out
      const style = getComputedStyle(el as HTMLElement);
      if (style.display === 'none' || style.visibility === 'hidden') continue;
      if (Number(style.opacity) < 0.05) {
        stranded.push(`${el.tagName.toLowerCase()}: ${(el.textContent ?? '').trim().slice(0, 50)}`);
      }
    }
    return stranded;
  }, selector);
}

test.describe('landing page motion', () => {
  test('the hero animates in and settles fully opaque', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    // toBeVisible() passes for a fully transparent element, so opacity is polled
    // rather than sampled once -- the entrance animation takes a few hundred ms,
    // and the thing that matters is that it finishes.
    await expect
      .poll(
        () =>
          page
            .getByRole('heading', { level: 1 })
            .evaluate((el) => Number(getComputedStyle(el).opacity)),
        { message: 'the h1 never finished animating in', timeout: 5000 },
      )
      .toBeGreaterThan(0.95);
  });

  test('no animated element is left stranded at zero opacity', async ({ page }) => {
    await page.goto('/');
    await scrollThrough(page);
    const stranded = await strandedCount(page, ANIMATED);
    expect(stranded, `invisible after scrolling: ${stranded.join(' | ')}`).toEqual([]);
  });

  test('the scroll-triggered sections actually animate in', async ({ page }) => {
    await page.goto('/');
    const steps = page.locator('[data-role="step"]');
    await expect(steps.first()).toBeAttached();
    await scrollThrough(page);
    // Every step in the band ends up visible, not just the first.
    const count = await steps.count();
    expect(count).toBeGreaterThan(1);
    for (let i = 0; i < count; i++) {
      await expect(steps.nth(i)).toBeVisible();
    }
  });

});

/**
 * Reduced motion gets an explicit context rather than `test.use()`: nested inside
 * another describe, `test.use({ reducedMotion })` did not apply, and the test then
 * passed/failed against the full-motion path instead -- which is exactly the
 * wrong-reason failure the media-query assertion below now makes impossible.
 */
test.describe('landing page with reduced motion', () => {
  test('all content is visible without scrolling at all', async ({ browser, baseURL }) => {
    const ctx = await browser.newContext({ baseURL, reducedMotion: 'reduce' });
    const page = await ctx.newPage();
    await page.goto('/');

    const reduced = await page.evaluate(
      () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    );
    expect(reduced, 'reduced-motion emulation did not apply').toBe(true);

    await page.waitForTimeout(600);
    // The reduced-motion path must skip the animation *and* its initial hidden
    // state -- skipping only the animation would hide the page permanently.
    const stranded = await strandedCount(page, ANIMATED);
    expect(stranded, `hidden under reduced motion: ${stranded.join(' | ')}`).toEqual([]);
    await ctx.close();
  });

  test('the page is still complete top to bottom', async ({ browser, baseURL }) => {
    const ctx = await browser.newContext({ baseURL, reducedMotion: 'reduce' });
    const page = await ctx.newPage();
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByRole('contentinfo')).toBeVisible();
    await ctx.close();
  });
});
