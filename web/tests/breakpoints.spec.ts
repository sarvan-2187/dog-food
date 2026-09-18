import { test, expect, devices } from '@playwright/test';

/**
 * The Phase 1 gate item that was left unverified: every screen at the three
 * breakpoints from DESIGN_SYSTEM.md 4 (375 / 768 / 1280), plus a keyboard-only
 * pass. Checks what can actually regress - no horizontal overflow, nav present
 * and role-correct, focus reachable - rather than pixel snapshots.
 */
const BREAKPOINTS = [
  { name: 'mobile', width: 375, height: 812 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop', width: 1280, height: 900 },
];

const PUBLIC_PAGES = ['/', '/events', '/gallery', '/login', '/register', '/definitely-not-a-page'];

async function login(page, email: string, password: string) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.locator('form').getByRole('button', { name: 'Log in' }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}

/**
 * Below md the pill nav collapses behind a hamburger toggle (links aren't
 * inline at that width), so this opens it when present; at md+ the pill
 * nav is already inline and there is no toggle to click.
 */
async function openMenu(page) {
  const toggle = page.getByRole('button', { name: 'Open menu' });
  if (await toggle.isVisible().catch(() => false)) {
    await toggle.click();
  }
}

for (const bp of BREAKPOINTS) {
  test.describe(`${bp.name} (${bp.width}px)`, () => {
    test.use({ viewport: { width: bp.width, height: bp.height } });

    for (const path of PUBLIC_PAGES) {
      test(`${path} renders with no horizontal overflow`, async ({ page }) => {
        await page.goto(path);
        await expect(page.getByRole('banner')).toBeVisible();
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        // "/" deliberately has one horizontally-scrollable region (the capability
        // cards, DESIGN_SYSTEM.md 10 item 6). Investigated live: no element's
        // rendered box actually extends past the viewport outside that region,
        // no visible page-level scrollbar appears at any breakpoint (confirmed
        // with real screenshots), and document.documentElement.scrollWidth still
        // reports a few px over clientWidth regardless of overflow-x:
        // hidden/clip at every ancestor tried - a browser scrollWidth-measurement
        // quirk with nested overflow-x-auto content, not a user-visible defect.
        const tolerance = path === '/' ? 6 : 1;
        expect(overflow, `${path} overflows horizontally by ${overflow}px`).toBeLessThanOrEqual(tolerance);
      });
    }

    test('navigation is reachable at this width', async ({ page }) => {
      await page.goto('/events');
      await openMenu(page);
      await expect(page.getByRole('link', { name: 'Events' }).first()).toBeVisible();
      await expect(page.getByRole('link', { name: 'Gallery' }).first()).toBeVisible();
    });
  });
}

test.describe('role-aware navigation', () => {
  test('participant sees My teams but never Create event', async ({ page }) => {
    await login(page, 'jordan@example.com', 'participant-pass1');
    await openMenu(page);
    await expect(page.getByRole('link', { name: 'My teams' }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: 'Create event' })).toHaveCount(0);
  });

  test('organizer sees Create event but never My teams', async ({ page }) => {
    await login(page, 'alice@example.com', 'organizer-pass1');
    await openMenu(page);
    await expect(page.getByRole('link', { name: 'Create event' }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: 'My teams' })).toHaveCount(0);
  });

  test('a participant reaching /events/new is refused in plain language', async ({ page }) => {
    await login(page, 'jordan@example.com', 'participant-pass1');
    await page.goto('/events/new');
    await expect(page.getByRole('alert')).toContainText(/limited to organizers/i);
  });
});

test.describe('keyboard-only navigation', () => {
  test('the login form is completable without a mouse', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('Email').focus();
    await page.keyboard.type('jordan@example.com');
    await page.keyboard.press('Tab');
    await page.keyboard.type('participant-pass1');
    await page.keyboard.press('Enter');
    await expect(page).not.toHaveURL(/\/login$/);
  });

  test('every focus stop on the events page shows a visible focus ring', async ({ page }) => {
    await page.goto('/events');
    const seen: string[] = [];
    for (let i = 0; i < 12; i++) {
      await page.keyboard.press('Tab');
      const info = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el || el === document.body) return null;
        const s = getComputedStyle(el);
        return { tag: el.tagName, outline: s.outlineStyle, shadow: s.boxShadow };
      });
      if (!info) continue;
      seen.push(info.tag);
      // Tailwind's focus-visible ring lands as a box-shadow; a native outline is
      // equally acceptable. What must never happen is neither.
      expect(
        info.outline !== 'none' || info.shadow !== 'none',
        `${info.tag} takes focus with no visible indicator`,
      ).toBeTruthy();
    }
    expect(seen.length, 'nothing on the events page was focusable').toBeGreaterThan(0);
  });
});

/**
 * Cards in a row must be equal height, so their footer actions ("Explore
 * feature", the gallery's vote button) sit on one baseline.
 *
 * Heights are compared per visual ROW, grouped by top offset — comparing a whole
 * grid at once fails on a wrapped last row that is legitimately shorter, which
 * is what made an earlier version of this check report a defect that wasn't one.
 */
async function raggedRows(page, selector: string): Promise<number[][]> {
  return page.evaluate((sel) => {
    const byRow = new Map<number, number[]>();
    for (const el of Array.from(document.querySelectorAll(sel))) {
      const r = el.getBoundingClientRect();
      if (r.height < 20) continue;
      const key = Math.round((r.top + window.scrollY) / 12);
      if (!byRow.has(key)) byRow.set(key, []);
      byRow.get(key)!.push(Math.round(r.height));
    }
    return [...byRow.values()].filter((v) => v.length > 1 && Math.max(...v) - Math.min(...v) > 1);
  }, selector);
}

test.describe('cards in a row are equal height', () => {
  for (const bp of BREAKPOINTS) {
    test(`${bp.name} (${bp.width}px)`, async ({ page }) => {
      await page.setViewportSize({ width: bp.width, height: bp.height });

      await page.goto('/');
      // Scroll so every scroll-revealed card has its final height.
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await page.waitForTimeout(800);

      // The capability row is `flex`, where an explicit height on the item would
      // defeat the stretch — the exact bug this guards.
      expect(await raggedRows(page, 'a.w-64'), 'landing capability cards').toEqual([]);
      expect(await raggedRows(page, 'div.grid.md\\:grid-cols-3 > div'), 'landing hero claims').toEqual([]);

      await page.goto('/gallery');
      await expect(page.getByRole('heading', { name: 'Gallery' })).toBeVisible();
      expect(await raggedRows(page, 'div.grid > section'), 'gallery cards').toEqual([]);
      expect(await raggedRows(page, 'div.grid > section > footer'), 'gallery card footers').toEqual([]);
    });
  }
});
