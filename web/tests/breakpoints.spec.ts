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
  await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible();
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
        expect(overflow, `${path} overflows horizontally by ${overflow}px`).toBeLessThanOrEqual(1);
      });
    }

    test('navigation is reachable at this width', async ({ page }) => {
      await page.goto('/events');
      await expect(page.getByRole('link', { name: 'Events' }).first()).toBeVisible();
      await expect(page.getByRole('link', { name: 'Gallery' }).first()).toBeVisible();
    });
  });
}

test.describe('role-aware navigation', () => {
  test('participant sees My teams but never Create event', async ({ page }) => {
    await login(page, 'jordan@example.com', 'participant-pass1');
    await expect(page.getByRole('link', { name: 'My teams' }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: 'Create event' })).toHaveCount(0);
  });

  test('organizer sees Create event but never My teams', async ({ page }) => {
    await login(page, 'alice@example.com', 'organizer-pass1');
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
    await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible();
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
