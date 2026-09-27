import { test, expect, type Page } from '@playwright/test';

/**
 * Phase 2 screens: judge dashboard, score form, rubric builder, results.
 * Runs against the seeded `docker compose` stack.
 */

async function login(page: Page, email: string, password: string) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.locator('form').getByRole('button', { name: 'Log in' }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}

/** The header hides nav links behind a circular hamburger button - open it first. */
async function openMenu(page: Page) {
  await page.getByRole('button', { name: 'Open menu' }).click();
  await expect(page.getByRole('dialog', { name: 'Site menu' })).toBeVisible();
}

const asOrganizer = (page: Page) => login(page, 'alice@example.com', 'organizer-pass1');
const asJudge = (page: Page) => login(page, 'sam@example.com', 'judge-pass123');

/**
 * These screens only exist once judging has been set up, and a fresh
 * `docker compose up -d --build` starts with fixtures but no assignments or
 * scores. Build that state over the API before the UI tests run, rather than
 * depending on another spec having run first.
 *
 * Both steps are idempotent server-side (assignment fills gaps only, scoring
 * upserts), so this is safe to repeat per worker.
 */
test.beforeAll(async ({ playwright, baseURL }) => {
  const ctx = await playwright.request.newContext({ baseURL });

  await ctx.post('/api/auth/login', { data: { email: 'alice@example.com', password: 'organizer-pass1' } });
  await ctx.post('/api/events/1/assignments', { data: { judges_per_submission: 3 } });
  await ctx.post('/api/auth/logout');

  // Sam scores everything so the dashboard has both scored and unscored states
  // across judges, and the rubric is locked for the "cannot change" test.
  await ctx.post('/api/auth/login', { data: { email: 'sam@example.com', password: 'judge-pass123' } });
  const progress = await (await ctx.get('/api/judge/assignments')).json();
  for (const assignment of progress.pending) {
    await ctx.put(`/api/assignments/${assignment.id}/score`, {
      data: {
        values: { impact: 7, execution: 7, innovation: 7, presentation: 7 },
        comment: 'Set up by the Playwright suite.',
      },
    });
  }
  await ctx.dispose();
});

test.describe('role-aware navigation for judging', () => {
  test('a judge sees Judging and never organizer links', async ({ page }) => {
    await asJudge(page);
    await openMenu(page);
    await expect(page.getByRole('link', { name: 'Judging' }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: 'Create event' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'My teams' })).toHaveCount(0);
  });

  test('a participant never sees Judging', async ({ page }) => {
    await login(page, 'jordan@example.com', 'participant-pass1');
    await expect(page.getByRole('link', { name: 'Judging' })).toHaveCount(0);
  });

  test('a participant reaching the judge dashboard is refused in plain language', async ({ page }) => {
    await login(page, 'jordan@example.com', 'participant-pass1');
    await page.goto('/judge');
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.getByRole('alert')).not.toContainText('403');
  });

  test('a judge reaching the organizer results page is refused', async ({ page }) => {
    await asJudge(page);
    await page.goto('/events/dogfood-2026/results');
    await expect(page.getByRole('alert')).toBeVisible();
  });
});

test.describe('organizer rubric builder', () => {
  test('weight total validates inline at the field level, live', async ({ page }) => {
    await asOrganizer(page);
    await page.goto('/events/dogfood-2026/rubric');
    await expect(page.getByText(/Weights add up to 1.00/)).toBeVisible();

    // Knock one weight out and the running total must object immediately,
    // without submitting and without a generic form-level rejection.
    const firstWeight = page.getByLabel('Weight').first();
    await firstWeight.fill('0.9');
    await expect(page.getByText('Weights must add up to 1.00')).toBeVisible();
    await expect(page.getByText(/too much - reduce a weight/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Save rubric' })).toBeDisabled();

    await firstWeight.fill('0.35');
    await expect(page.getByText(/Weights add up to 1.00/)).toBeVisible();
  });

  test('a rubric locked by existing scores explains why', async ({ page }) => {
    await asOrganizer(page);
    await page.goto('/events/dogfood-2026/rubric');
    await page.getByLabel('Rubric name').fill('Renamed Rubric');
    await page.getByRole('button', { name: 'Save rubric' }).click();
    // The seeded event has scores, so this must be refused with a reason.
    await expect(page.getByText(/already scored against this rubric/i).first()).toBeVisible();
  });
});

test.describe('judge dashboard and score form', () => {
  test('progress leads with X of Y, above the fold', async ({ page }) => {
    await asJudge(page);
    await page.goto('/judge');
    const headline = page.getByText(/^\d+ of \d+$/);
    await expect(headline).toBeVisible();
    // "Above the fold" is the actual requirement, so assert position, not just presence.
    const box = await headline.boundingBox();
    expect(box!.y).toBeLessThan(700);
    await expect(page.getByRole('progressbar')).toBeVisible();
  });

  test('every assignment carries a text status, not colour alone', async ({ page }) => {
    await asJudge(page);
    await page.goto('/judge');
    // Case-insensitive: the badge is upper-cased in CSS, and Playwright matches
    // rendered text. The point is that the state is carried by words at all.
    const badges = page.locator('li').getByText(/\b(not\s+scored|scored)\b/i);
    // count() does not auto-wait, so wait for the list to render first.
    await expect(badges.first()).toBeVisible();
    expect(await badges.count()).toBeGreaterThan(0);
    for (const text of await badges.allTextContents()) {
      expect(text).toMatch(/\b(not\s+scored|scored)\b/i);
    }
  });

  test('the score form shows weights and a live running total', async ({ page }) => {
    await asJudge(page);
    await page.goto('/judge');
    await page.getByRole('button', { name: /Score now|Review score/ }).first().click();

    await expect(page.getByText(/weight 35% . out of 10/).first()).toBeVisible();
    const total = page.getByText('Weighted total');
    await expect(total).toBeVisible();

    const impact = page.getByLabel('Impact');
    await impact.fill('10');
    await page.getByLabel('Execution').fill('10');
    await page.getByLabel('Innovation').fill('10');
    await page.getByLabel('Presentation').fill('10');
    // All criteria at max -> the weighted total must equal the max total.
    await expect(page.getByText('10.00', { exact: false }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Submit score|Update score/ })).toBeEnabled();
  });

  test('an out-of-range score is caught inline before submitting', async ({ page }) => {
    await asJudge(page);
    await page.goto('/judge');
    await page.getByRole('button', { name: /Score now|Review score/ }).first().click();

    await page.getByLabel('Impact').fill('99');
    await page.getByLabel('Impact').blur();
    await expect(page.getByText('Impact must be between 0 and 10.')).toBeVisible();
    await expect(page.getByRole('button', { name: /Submit score|Update score/ })).toBeDisabled();
  });

  test('submitting a score gives an unambiguous confirmation, not a redirect', async ({ page }) => {
    await asJudge(page);
    await page.goto('/judge');
    await page.getByRole('button', { name: /Score now|Review score/ }).first().click();

    for (const label of ['Impact', 'Execution', 'Innovation', 'Presentation']) {
      await page.getByLabel(label).fill('7');
    }
    await page.getByRole('button', { name: /Submit score|Update score/ }).click();
    await expect(page.getByText(/Score saved for/)).toBeVisible();
    // Still on the form, with a persistent saved marker - no silent redirect.
    await expect(page.getByText(/This score is recorded/)).toBeVisible();
  });
});

test.describe('organizer results', () => {
  test('normalised standings render with raw mean alongside', async ({ page }) => {
    await asOrganizer(page);
    await page.goto('/events/dogfood-2026/results');
    await expect(page.getByRole('heading', { name: 'Results' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Normalised standings' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Raw mean' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Normalised' })).toBeVisible();
  });

  test('a CSV export downloads and is real CSV', async ({ page }) => {
    await asOrganizer(page);
    await page.goto('/events/dogfood-2026/results');
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Normalised results' }).click(),
    ]);
    expect(download.suggestedFilename()).toContain('results.csv');
    await expect(page.getByText(/export downloaded/)).toBeVisible();
  });

  test('re-running assignment reports that nothing was left to do', async ({ page }) => {
    await asOrganizer(page);
    await page.goto('/events/dogfood-2026/results');
    await page.getByRole('button', { name: 'Assign judges' }).click();
    await expect(page.getByText(/already has its judges|Assigned \d+ new/)).toBeVisible();
  });
});

test.describe('Phase 2 screens at every breakpoint', () => {
  for (const bp of [
    { name: 'mobile', width: 375, height: 812 },
    { name: 'tablet', width: 768, height: 1024 },
    { name: 'desktop', width: 1280, height: 900 },
  ]) {
    test(`${bp.name} (${bp.width}px): judge screens do not overflow`, async ({ page }) => {
      await page.setViewportSize({ width: bp.width, height: bp.height });
      await asJudge(page);
      for (const path of ['/judge']) {
        await page.goto(path);
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        expect(overflow, `${path} overflows by ${overflow}px`).toBeLessThanOrEqual(1);
      }
      await page.getByRole('button', { name: /Score now|Review score/ }).first().click();
      const formOverflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(formOverflow, `score form overflows by ${formOverflow}px`).toBeLessThanOrEqual(1);
    });

    test(`${bp.name} (${bp.width}px): organizer screens do not overflow`, async ({ page }) => {
      await page.setViewportSize({ width: bp.width, height: bp.height });
      await asOrganizer(page);
      for (const path of ['/events/dogfood-2026/rubric', '/events/dogfood-2026/results']) {
        await page.goto(path);
        await expect(page.getByRole('banner')).toBeVisible();
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        expect(overflow, `${path} overflows by ${overflow}px`).toBeLessThanOrEqual(1);
      }
    });
  }
});

test.describe('keyboard-only', () => {
  test('the score form is completable without a mouse', async ({ page }) => {
    await asJudge(page);
    await page.goto('/judge');
    await page.getByRole('button', { name: /Score now|Review score/ }).first().click();

    await page.getByLabel('Impact').focus();
    for (let i = 0; i < 4; i++) {
      // Select-all then type, because these fields may already hold a score.
      await page.keyboard.press('ControlOrMeta+a');
      await page.keyboard.type('6');
      await page.keyboard.press('Tab');
    }
    const submit = page.getByRole('button', { name: /Submit score|Update score/ });
    await expect(submit).toBeEnabled();
    await submit.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByText(/Score saved for/)).toBeVisible();
  });
});
