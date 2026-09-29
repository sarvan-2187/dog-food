import { expect, test } from '@playwright/test';

/**
 * Event stages, API keys, certificate verification and the events archive:
 * the screens behind the README's ten-stage walkthrough.
 */
async function login(page, email: string, password: string) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel(/^Password/).fill(password);
  await page.locator('form').getByRole('button', { name: 'Log in' }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}

test('an organizer adds a stage and participants see it on the event page', async ({ page }) => {
  await login(page, 'alice@example.com', 'organizer-pass1');
  await page.goto('/events/dogfood-2026/settings');
  const editor = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Stages', exact: true }) });
  await editor.getByRole('button', { name: 'Add stage' }).click();
  // The new stage is always last; counting first would race the page's own load.
  const stage = editor.getByRole('group').last();
  const name = `Demo day ${Date.now()}`.slice(0, 40);
  await stage.getByLabel('Name').fill(name);
  await editor.getByRole('button', { name: 'Save stages' }).click();
  await expect(page.getByText('Stages saved.')).toBeVisible();

  await page.goto('/events/dogfood-2026');
  await expect(page.getByRole('list', { name: 'Event stages' }).getByText(name)).toBeVisible();

  // Leave the seeded stages as they were for the next run.
  const ev = await (await page.request.get('/api/events/dogfood-2026')).json();
  await page.request.patch(`/api/events/${ev.id}`, {
    data: { stages: ev.stages.filter((s: { name: string }) => s.name !== name) },
  });
});

test('an API key is created once, works as a bearer token, and can be revoked', async ({ page, playwright, baseURL }) => {
  await login(page, 'alice@example.com', 'organizer-pass1');
  await page.goto('/integrations');
  const keyName = `E2E key ${Date.now()}`.slice(0, 40);
  await page.getByLabel('New key name').fill(keyName);
  await page.getByRole('button', { name: 'Create key' }).click();
  const key = (await page.locator('code').filter({ hasText: /^hf_/ }).textContent())!.trim();
  expect(key).toMatch(/^hf_/);

  const server = await playwright.request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer ${key}` } });
  expect((await (await server.get('/api/auth/me')).json()).email).toBe('alice@example.com');

  page.once('dialog', (d) => d.accept());
  await page
    .getByRole('list', { name: 'Your API keys' })
    .locator('li', { hasText: keyName })
    .getByRole('button', { name: 'Revoke' })
    .click();
  await expect(page.getByText(`"${keyName}" was revoked.`)).toBeVisible();
  expect((await server.get('/api/auth/me')).status()).toBe(401);
  await server.dispose();
});

test('a participant never sees Integrations', async ({ page }) => {
  await login(page, 'jordan@example.com', 'participant-pass1');
  await expect(page.getByRole('link', { name: 'Integrations', exact: true })).toHaveCount(0);
});

test('a made-up certificate code is not verified', async ({ page }) => {
  await page.goto('/verify/HF-1-0000000000');
  await expect(page.getByText('No match')).toBeVisible();
});

test('past events are one filter away', async ({ page }) => {
  await page.goto('/events');
  await page.getByRole('tab', { name: /Past events/ }).click();
  await page.getByLabel('Search events').fill('Sample Hack');
  await expect(page.getByRole('link', { name: /Sample Hack 2026/ })).toBeVisible();
});
