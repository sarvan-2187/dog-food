import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';

/**
 * The guided tour (PLAN.md Phase 8). This is the one spec that opts out of the
 * suite-wide suppression in tour-state.ts, so it starts with genuinely empty
 * storage and sees the tour exactly as a first-time user does.
 */
test.use({ storageState: { cookies: [], origins: [] } });

const popover = '.driver-popover.hackflow-tour';

async function logIn(page: Page, email: string, password: string) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel(/^Password/).fill(password);
  await page.locator('form').getByRole('button', { name: 'Log in' }).click();
}

test.describe('guided tour', () => {
  test('greets a first-time participant, then stays gone once dismissed', async ({ page }) => {
    await logIn(page, 'jordan@example.com', 'participant-pass1');

    await expect(page.locator(popover)).toBeVisible();
    await expect(page.getByText('Welcome to HackFlow')).toBeVisible();

    await page.locator(popover).getByRole('button', { name: 'Close' }).click();
    await expect(page.locator(popover)).toBeHidden();

    // Dismissing records it as seen, so a reload must not reopen it. The wait is
    // longer than the tour's own start delay - asserting immediately would pass
    // even if the tour were about to appear.
    await page.reload();
    await page.waitForTimeout(1500);
    await expect(page.locator(popover)).toHaveCount(0);
  });

  test('is replayable on demand from the profile page', async ({ page }) => {
    await logIn(page, 'jordan@example.com', 'participant-pass1');
    await page.locator(popover).getByRole('button', { name: 'Close' }).click();

    await page.getByRole('link', { name: 'Profile' }).click();
    await page.getByRole('button', { name: 'Replay the guided tour' }).click();

    await expect(page.locator(popover)).toBeVisible();
  });

  test('a judge is given judging guidance, not the participant script', async ({ page }) => {
    await logIn(page, 'sam@example.com', 'judge-pass123');

    await expect(page.locator(popover)).toBeVisible();
    await page.locator(popover).getByRole('button', { name: 'Next' }).click();

    // The role-specific proof: this step exists only in the judge tour.
    await expect(page.getByText(/your judging list/i)).toBeVisible();
  });

  test('an organizer is given organizing guidance', async ({ page }) => {
    await logIn(page, 'alice@example.com', 'organizer-pass1');

    await expect(page.locator(popover)).toBeVisible();
    await page.locator(popover).getByRole('button', { name: 'Next' }).click();

    await expect(page.getByText(/your events/i)).toBeVisible();
  });

  test('a signed-out visitor is never interrupted by it', async ({ page }) => {
    await page.goto('/events');
    await page.waitForTimeout(1500);

    await expect(page.locator(popover)).toHaveCount(0);
  });
});
