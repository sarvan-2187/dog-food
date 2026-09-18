import { test, expect, type Page } from '@playwright/test';

/** Judge invitation — the only route into the `judge` role. */

async function login(page: Page, email: string, password: string) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.locator('form').getByRole('button', { name: 'Log in' }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}

async function register(page: Page, email: string, name: string) {
  await page.goto('/register');
  await page.getByLabel('Name').fill(name);
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill('supersecret1');
  await page.locator('form').getByRole('button', { name: 'Sign up' }).click();
  await expect(page).not.toHaveURL(/\/register$/);
}

/**
 * No-op: the header (rebuilt as a persistent pill nav) shows every link
 * inline at every width now - nothing to open.
 */
async function openMenu(_page: Page) {
  // intentionally empty
}

const asOrganizer = (page: Page) => login(page, 'alice@example.com', 'organizer-pass1');

/** Issue an invite as the organizer and return its redemption path. */
async function issueInvite(page: Page, email: string): Promise<string> {
  await asOrganizer(page);
  await page.goto('/events/dogfood-2026/results');
  await expect(page.getByRole('heading', { name: 'Judges' })).toBeVisible();
  await page.getByLabel('Their email').fill(email);
  await page.getByRole('button', { name: 'Create invitation' }).click();
  await expect(page.getByText(/Invitation created/)).toBeVisible();

  const link = page.locator('code', { hasText: '/judge-invite/' }).first();
  await expect(link).toBeVisible();
  const url = (await link.textContent()) ?? '';
  return new URL(url.trim()).pathname;
}

test.describe('organizer issues invitations', () => {
  // Headless Chromium denies clipboard access by default, which sends the copy
  // button down its (correct) failure path instead of the one under test.
  test.use({ permissions: ['clipboard-read', 'clipboard-write'] });

  test('an invitation can be created, copied and revoked', async ({ page }) => {
    const path = await issueInvite(page, `invitee-${Date.now()}@example.com`);
    expect(path).toContain('/judge-invite/');

    await expect(page.getByText('Awaiting acceptance').first()).toBeVisible();
    await page.getByRole('button', { name: 'Copy link' }).first().click();
    await expect(page.getByRole('button', { name: 'Copied' }).first()).toBeVisible();

    await page.getByRole('button', { name: 'Revoke' }).first().click();
    await expect(page.getByText(/no longer works/)).toBeVisible();
  });

  test('the panel is invisible to a judge', async ({ page }) => {
    await login(page, 'sam@example.com', 'judge-pass123');
    await page.goto('/events/dogfood-2026/results');
    // The whole page is organizer-gated, so a judge gets the refusal, not the panel.
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Judges' })).toHaveCount(0);
  });
});

test.describe('redeeming an invitation', () => {
  test('a participant accepts and becomes a judge, and the nav updates', async ({ page, browser }) => {
    const email = `newjudge-${Date.now()}@example.com`;
    const path = await issueInvite(page, email);

    const ctx = await browser.newContext({ baseURL: 'http://localhost:8000' });
    const invitee = await ctx.newPage();
    await register(invitee, email, 'New Judge');
    // Role-aware nav: no Judging link before accepting.
    await openMenu(invitee);
    await expect(invitee.getByRole('link', { name: 'Judging' })).toHaveCount(0);
    await invitee.keyboard.press('Escape');

    await invitee.goto(path);
    // It must state the consequence and wait for a press, never redeem on load.
    await expect(invitee.getByText(/gives .* the judge role/)).toBeVisible();
    await invitee.getByRole('button', { name: 'Accept and become a judge' }).click();

    await expect(invitee.getByText("You're a judge now")).toBeVisible();
    // refresh() means the nav reflects the new role without a manual reload.
    await openMenu(invitee);
    await expect(invitee.getByRole('link', { name: 'Judging' }).first()).toBeVisible();
    await invitee.keyboard.press('Escape');

    await invitee.goto('/judge');
    await expect(invitee.getByRole('heading', { name: 'Judging' })).toBeVisible();
    await ctx.close();
  });

  test('a second person cannot reuse the same link', async ({ page, browser }) => {
    const path = await issueInvite(page, `first-${Date.now()}@example.com`);

    const ctxA = await browser.newContext({ baseURL: 'http://localhost:8000' });
    const first = await ctxA.newPage();
    await register(first, `usedby-${Date.now()}@example.com`, 'First Accepter');
    await first.goto(path);
    await first.getByRole('button', { name: 'Accept and become a judge' }).click();
    await expect(first.getByText("You're a judge now")).toBeVisible();
    await ctxA.close();

    const ctxB = await browser.newContext({ baseURL: 'http://localhost:8000' });
    const second = await ctxB.newPage();
    await register(second, `second-${Date.now()}@example.com`, 'Second Accepter');
    await second.goto(path);
    await expect(second.getByText('This invitation is no longer valid')).toBeVisible();
    await expect(second.getByText(/already been used/)).toBeVisible();
    await ctxB.close();
  });

  test('a signed-out visitor is sent through auth and back, not refused', async ({ page, browser }) => {
    const path = await issueInvite(page, `signedout-${Date.now()}@example.com`);

    const ctx = await browser.newContext({ baseURL: 'http://localhost:8000' });
    const visitor = await ctx.newPage();
    await visitor.goto(path);
    await expect(visitor.getByText("You've been invited to judge")).toBeVisible();
    const cta = visitor.getByRole('link', { name: 'Log in and accept' });
    await expect(cta).toBeVisible();
    // The return path must be preserved so they land back here after signing in.
    await expect(cta).toHaveAttribute('href', new RegExp(`next=${path.replace(/\//g, '\\/')}`));
    await ctx.close();
  });

  test('an organizer following a judge link is warned, not silently demoted', async ({ page }) => {
    const path = await issueInvite(page, `orgself-${Date.now()}@example.com`);
    await page.goto(path);
    await expect(page.getByRole('alert')).toContainText(/remove your ability to run events/);
    await expect(page.getByRole('button', { name: 'Accept and become a judge' })).toBeDisabled();
    // Still an organizer.
    await openMenu(page);
    await expect(page.getByRole('link', { name: 'Create event' }).first()).toBeVisible();
  });

  test('a dead token explains itself instead of erroring', async ({ page, browser }) => {
    const ctx = await browser.newContext({ baseURL: 'http://localhost:8000' });
    const visitor = await ctx.newPage();
    await visitor.goto('/judge-invite/definitely-not-a-real-token');
    await expect(visitor.getByText('This invitation is no longer valid')).toBeVisible();
    await expect(visitor.getByText(/not valid/)).toBeVisible();
    await ctx.close();
  });
});

test.describe('the Select is a real listbox', () => {
  test('the expiry dropdown is keyboard-operable and announces itself', async ({ page }) => {
    await asOrganizer(page);
    await page.goto('/events/dogfood-2026/results');

    const trigger = page.getByRole('combobox', { name: 'Expires in' });
    await expect(trigger).toBeVisible();
    await trigger.focus();
    await page.keyboard.press('Enter');
    // Radix renders a real listbox, which a native styled <div> would not.
    await expect(page.getByRole('listbox')).toBeVisible();
    await page.getByRole('option', { name: '30 days' }).click();
    await expect(trigger).toContainText('30 days');
  });

  test('the gallery order dropdown still works after the shadcn swap', async ({ page }) => {
    await page.goto('/events/dogfood-2026/gallery');
    const trigger = page.getByRole('combobox', { name: 'Order' });
    await expect(trigger).toBeVisible();
    await trigger.click();
    await expect(page.getByRole('listbox')).toBeVisible();
    await page.getByRole('option', { name: 'Shuffled' }).click();
    await expect(trigger).toContainText('Shuffled');
  });
});
