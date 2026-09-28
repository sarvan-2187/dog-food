import { test, expect, type Page } from '@playwright/test';

/** Phase 3: community voting, comments, results hiding, stable shuffle. */

async function login(page: Page, email: string, password: string) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.locator('form').getByRole('button', { name: 'Log in' }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}

const asVoter = (page: Page) => login(page, 'kai@example.com', 'participant-pass3');
const asOrganizer = (page: Page) => login(page, 'alice@example.com', 'organizer-pass1');

/**
 * The "Order" control is a Radix Select (a button + listbox), not a native
 * <select> - .selectOption() only works on the latter. Real keyboard/roving
 * focus accessibility was the point of switching to Radix, so drive it the
 * way a user actually would: open the trigger, click the option by its label.
 */
async function selectOrder(page: Page, label: string) {
  await page.getByLabel('Order').click();
  await page.getByRole('option', { name: label }).click();
}

test.describe('results hiding', () => {
  test('the gallery explains why counts are hidden, not just that they are', async ({ page }) => {
    await asVoter(page);
    await page.goto('/gallery');
    await expect(page.getByText(/Vote counts are hidden until voting closes/)).toBeVisible();
    // The *reason* must be present, not only the fact.
    await expect(page.getByText(/everyone sees the totals at the same time/i)).toBeVisible();
  });

  test('a card shows a labelled placeholder rather than a wrong number', async ({ page }) => {
    await asVoter(page);
    await page.goto('/gallery');
    await expect(page.getByText('Counts hidden until voting closes').first()).toBeVisible();
  });

  test('sorting by votes is refused while results are hidden, in plain language', async ({ page }) => {
    await asVoter(page);
    await page.goto('/gallery');
    await selectOrder(page, 'Most votes');
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.getByRole('alert')).not.toContainText('425');
  });
});

test.describe('voting', () => {
  test('a vote toggles optimistically and persists across a reload', async ({ page }) => {
    await asVoter(page);
    await page.goto('/gallery');

    const vote = page.getByRole('button', { name: 'Vote for this submission' }).first();
    await expect(vote).toBeVisible();
    await vote.click();
    // Optimistic: the label flips without waiting for the round trip.
    await expect(page.getByRole('button', { name: 'Remove your vote' }).first()).toBeVisible();

    await page.reload();
    await expect(page.getByRole('button', { name: 'Remove your vote' }).first()).toBeVisible();
  });

  test('a vote can be withdrawn', async ({ page }) => {
    await asVoter(page);
    await page.goto('/gallery');
    const voted = page.getByRole('button', { name: 'Remove your vote' }).first();
    if (await voted.count()) {
      await voted.click();
      await expect(page.getByRole('button', { name: 'Vote for this submission' }).first()).toBeVisible();
    }
  });

  test('a signed-out visitor is invited to log in rather than shown a dead control', async ({ page }) => {
    await page.goto('/gallery');
    await expect(page.getByRole('link', { name: 'Log in to vote' }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Vote for this submission' })).toHaveCount(0);
  });
});

test.describe('comments', () => {
  test('a comment appears optimistically, then settles', async ({ page }) => {
    await asVoter(page);
    await page.goto('/gallery');
    await page.getByRole('link', { name: /comment|Add the first comment/ }).first().click();

    const text = `Playwright comment ${Date.now()}`;
    await page.getByLabel('Add a comment').fill(text);
    await page.getByRole('button', { name: 'Post comment' }).click();

    await expect(page.getByText(text)).toBeVisible();
    // The pending marker clears once the server confirms.
    await expect(page.getByText('Sending...')).toHaveCount(0, { timeout: 10_000 });

    await page.reload();
    await expect(page.getByText(text)).toBeVisible();
  });

  test('an over-short comment cannot be posted', async ({ page }) => {
    await asVoter(page);
    await page.goto('/gallery');
    await page.getByRole('link', { name: /comment|Add the first comment/ }).first().click();
    await expect(page.getByRole('button', { name: 'Post comment' })).toBeDisabled();
    await page.getByLabel('Add a comment').fill('a');
    await expect(page.getByRole('button', { name: 'Post comment' })).toBeDisabled();
    await page.getByLabel('Add a comment').fill('long enough');
    await expect(page.getByRole('button', { name: 'Post comment' })).toBeEnabled();
  });

  test('the author can delete their own comment', async ({ page }) => {
    await asVoter(page);
    await page.goto('/gallery');
    await page.getByRole('link', { name: /comment|Add the first comment/ }).first().click();

    const text = `Deletable ${Date.now()}`;
    await page.getByLabel('Add a comment').fill(text);
    await page.getByRole('button', { name: 'Post comment' }).click();
    await expect(page.getByText(text)).toBeVisible();
    await expect(page.getByText('Sending...')).toHaveCount(0, { timeout: 10_000 });

    await page.getByRole('listitem').filter({ hasText: text }).getByRole('button', { name: 'Delete' }).click();
    await expect(page.getByText(text)).toHaveCount(0);
  });
});

test.describe('shuffled ordering', () => {
  test('the order is stable across visits within one session', async ({ page }) => {
    const shuffled = async () => {
      await page.goto('/gallery');
      // Selecting the order triggers a refetch. Waiting only for an <h3> to be
      // visible is not enough -- the previous ordering is still on screen until
      // the new response renders, so the read has to be anchored to that
      // response, not to the mere presence of cards.
      const [response] = await Promise.all([
        page.waitForResponse(
          (r) => r.url().includes('/api/gallery') && r.url().includes('order=random') && r.ok(),
        ),
        selectOrder(page, 'Shuffled'),
      ]);
      const expected: string[] = (await response.json()).map((row: { title: string }) => row.title);
      // Wait for the DOM to actually reflect that response before reading it.
      await expect(page.locator('section h3')).toHaveText(expected);
      return expected;
    };

    const first = await shuffled();
    // Navigate away and back: same session, so the same order (no jank).
    await page.goto('/events');
    const second = await shuffled();

    // Other specs run in parallel against this same stack and may submit a new
    // entry between the two loads. What must hold is that the entries present in
    // both keep their relative order -- comparing the raw lists would make this
    // test fail for an unrelated insert rather than for real reshuffling.
    const common = new Set(first.filter((t) => second.includes(t)));
    expect(common.size, 'nothing in common between the two loads').toBeGreaterThan(1);
    expect(second.filter((t) => common.has(t))).toEqual(first.filter((t) => common.has(t)));
  });
});

test.describe('organizer voting controls', () => {
  test('voting can be closed and reopened', async ({ page }) => {
    await asOrganizer(page);
    await page.goto('/events/dogfood-2026/results');
    await expect(page.getByRole('heading', { name: 'Community voting' })).toBeVisible();

    await page.getByRole('button', { name: 'Close voting' }).click();
    await expect(page.getByText('Community voting is now closed.')).toBeVisible();

    await page.getByRole('button', { name: 'Open voting' }).click();
    await expect(page.getByText('Community voting is now open.')).toBeVisible();
  });
});

test.describe('Phase 3 screens at every breakpoint', () => {
  for (const bp of [
    { name: 'mobile', width: 375, height: 812 },
    { name: 'tablet', width: 768, height: 1024 },
    { name: 'desktop', width: 1280, height: 900 },
  ]) {
    test(`${bp.name} (${bp.width}px): gallery and submission detail do not overflow`, async ({ page }) => {
      await page.setViewportSize({ width: bp.width, height: bp.height });
      await asVoter(page);
      for (const path of ['/gallery', '/submissions/1']) {
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
  test('a comment can be written and posted without a mouse', async ({ page }) => {
    await asVoter(page);
    await page.goto('/submissions/1');
    const text = `Keyboard comment ${Date.now()}`;
    await page.getByLabel('Add a comment').focus();
    await page.keyboard.type(text);
    const post = page.getByRole('button', { name: 'Post comment' });
    await expect(post).toBeEnabled();
    await post.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByText(text)).toBeVisible();
  });

  test('the vote control is reachable and operable by keyboard', async ({ page }) => {
    await asVoter(page);
    await page.goto('/submissions/1');
    const vote = page.getByRole('button', { name: /Vote for this submission|Remove your vote/ });
    await vote.focus();
    const indicator = await vote.evaluate((el) => {
      const s = getComputedStyle(el);
      return s.outlineStyle !== 'none' || s.boxShadow !== 'none';
    });
    expect(indicator, 'the vote control takes focus with no visible indicator').toBeTruthy();
    const before = await vote.getAttribute('aria-pressed');
    await page.keyboard.press('Enter');
    await expect(vote).toHaveAttribute('aria-pressed', before === 'true' ? 'false' : 'true');
  });
});
