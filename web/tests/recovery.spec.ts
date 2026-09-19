import { expect, test } from '@playwright/test';
import type { APIRequestContext, Page } from '@playwright/test';

/**
 * PLAN.md Phase 9 - forgotten passwords, end to end in a real browser.
 *
 * Every test resets the password of a participant it registers itself, never
 * a seeded account: the other specs sign in as the fixtures in parallel.
 *
 * The emailed flow needs the local Mailpit inbox:
 *   docker compose -f docker-compose.yml -f docker-compose.mail.yml up
 * and is skipped when it isn't running, so the default stack stays green.
 */

const MAILPIT = process.env.MAILPIT_URL ?? 'http://localhost:8025';
const NEW_PASSWORD = 'fresh-password-9';

async function freshParticipant(request: APIRequestContext) {
  const email = `recovery-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  const r = await request.post('/api/auth/register', {
    data: { email, password: 'original-pass-1', name: 'Rhea Recovery' },
  });
  expect(r.ok()).toBeTruthy();
  await request.post('/api/auth/logout');
  return email;
}

async function login(page: Page, email: string, password: string) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel(/^Password/).fill(password);
  await page.locator('form').getByRole('button', { name: 'Log in' }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

async function emailEnabled(request: APIRequestContext): Promise<boolean> {
  return (await (await request.get('/api/auth/recovery-options')).json()).email;
}

async function mailpitUp(request: APIRequestContext): Promise<boolean> {
  try {
    return (await request.get(`${MAILPIT}/api/v1/messages`, { timeout: 2000 })).ok();
  } catch {
    return false;
  }
}

async function resetLinkFromMailpit(request: APIRequestContext, to: string): Promise<string> {
  let id: string | undefined;
  await expect
    .poll(
      async () => {
        const list = await (await request.get(`${MAILPIT}/api/v1/messages`)).json();
        id = list.messages.find(
          (m: { To: { Address: string }[]; Subject: string }) =>
            m.To.some((t) => t.Address === to) && m.Subject === 'Reset your HackFlow password',
        )?.ID;
        return id;
      },
      { timeout: 15000 },
    )
    .toBeTruthy();
  const message = await (await request.get(`${MAILPIT}/api/v1/message/${id}`)).json();
  const link = (message.Text as string).split('\n').find((line) => line.includes('/reset/'));
  expect(link).toBeTruthy();
  return link!.trim();
}

test('the login page offers a way back in', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('link', { name: 'Forgot password?' }).click();
  await expect(page).toHaveURL(/\/forgot-password$/);
  await expect(page.getByRole('heading', { name: /forgot your password/i })).toBeVisible();
});

test('with email off, forgot password points at an organizer and asks for nothing', async ({ page, request }) => {
  test.skip(await emailEnabled(request), 'email is on in this stack');
  await page.goto('/forgot-password');
  await expect(page.getByText(/ask an organizer/i)).toBeVisible();
  await expect(page.getByLabel('Email')).toHaveCount(0);
});

test('an organizer link gets a locked-out participant back in', async ({ browser, page, request }) => {
  const email = await freshParticipant(request);

  await login(page, 'alice@example.com', 'organizer-pass1');
  await page.goto('/dashboard');
  const card = page.locator('[data-tour="help-sign-in"]');
  await card.getByLabel('Their email').fill(email);
  await card.getByRole('button', { name: 'Create reset link' }).click();
  const url = (await card.locator('code').textContent())!.trim();
  expect(url).toMatch(/\/reset\/[\w-]{20,}$/);
  await expect(card.getByText(/expires in \d+ min/i)).toBeVisible();

  // The participant opens it on their own device.
  const theirs = await browser.newContext({ storageState: undefined });
  const them = await theirs.newPage();
  await them.goto(new URL(url).pathname);
  await expect(them.getByText('Resetting the password for Rhea.')).toBeVisible();
  await them.getByLabel(/^New password/).fill(NEW_PASSWORD);
  await them.getByRole('button', { name: 'Save and sign in' }).click();
  await expect(them.getByRole('heading', { name: 'Password updated' })).toBeVisible();
  await expect(them.getByText(/created for you by Alice/i)).toBeVisible();

  // Signed in, and the link is spent.
  expect((await them.request.get('/api/auth/me')).ok()).toBeTruthy();
  await them.goto(new URL(url).pathname);
  await expect(them.getByText('This reset link has already been used.')).toBeVisible();
  await theirs.close();
});

test('an organizer cannot create a link for another organizer', async ({ page }) => {
  await login(page, 'alice@example.com', 'organizer-pass1');
  await page.goto('/dashboard');
  const card = page.locator('[data-tour="help-sign-in"]');
  await card.getByLabel('Their email').fill('priya@example.com');
  await card.getByRole('button', { name: 'Create reset link' }).click();
  await expect(card.getByRole('alert')).toContainText(/can't create a reset link/i);
});

test('a bad link explains itself instead of erroring', async ({ page }) => {
  await page.goto('/reset/not-a-real-link');
  await expect(page.getByRole('heading', { name: "This link can't be used" })).toBeVisible();
});

test('forgot password by email, start to finish, with no organizer involved', async ({ page, request }) => {
  test.skip(!(await emailEnabled(request)) || !(await mailpitUp(request)), 'needs docker-compose.mail.yml (Mailpit)');
  const email = await freshParticipant(request);

  await page.goto('/login');
  await page.getByRole('link', { name: 'Forgot password?' }).click();
  await page.getByLabel('Email').fill(email);
  await page.getByRole('button', { name: 'Send reset link' }).click();
  await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible();

  const link = await resetLinkFromMailpit(request, email);
  await page.goto(new URL(link).pathname);
  await page.getByLabel(/^New password/).fill(NEW_PASSWORD);
  await page.getByRole('button', { name: 'Save and sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Password updated' })).toBeVisible();

  // The new password is the one that works now.
  await page.getByRole('link', { name: 'Go to your dashboard' }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.context().clearCookies();
  await login(page, email, NEW_PASSWORD);
});

test('a signed-in user can change their password from the profile', async ({ page, request }) => {
  const email = await freshParticipant(request);
  await login(page, email, 'original-pass-1');
  await page.goto('/profile');
  await page.getByLabel(/^Current password/).fill('wrong-password');
  await page.getByLabel(/^New password/).fill(NEW_PASSWORD);
  await page.getByRole('button', { name: 'Change password' }).click();
  await expect(page.getByText('Your current password is incorrect.')).toBeVisible();

  await page.getByLabel(/^Current password/).fill('original-pass-1');
  await page.getByRole('button', { name: 'Change password' }).click();
  await expect(page.getByText(/every other device has been signed out/i)).toBeVisible();
});

for (const width of [375, 768, 1280]) {
  test(`recovery screens do not overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

    for (const path of ['/forgot-password', '/reset/not-a-real-link']) {
      await page.goto(path);
      await expect(page.getByRole('heading').first()).toBeVisible();
      expect(await overflow(), path).toBeLessThanOrEqual(0);
    }

    // The organizer card, with a long reset link showing - the widest state.
    await login(page, 'alice@example.com', 'organizer-pass1');
    await page.goto('/dashboard');
    const card = page.locator('[data-tour="help-sign-in"]');
    await card.getByLabel('Their email').fill('jordan@example.com');
    await card.getByRole('button', { name: 'Create reset link' }).click();
    await expect(card.locator('code')).toBeVisible();
    expect(await overflow(), '/dashboard').toBeLessThanOrEqual(0);
  });
}
