import { expect, test } from '@playwright/test';

/**
 * An event leaves as easily as it arrived (DOGFOOD T4): its backup carries team
 * members, the judge panel (with tracks), assignments and scores, and the
 * import panel restores all of them as a new event.
 */

const SHOWCASE = 'judging-showcase-2026'; // seeded with a judge panel, two of them on tracks

const uid = () => `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;

test('an event backup restores its people and judge panel through the import panel', async ({
  page,
  playwright,
  baseURL,
}) => {
  const org = await playwright.request.newContext({ baseURL });
  expect((await org.post('/api/auth/login', { data: { email: 'alice@example.com', password: 'organizer-pass1' } })).ok()).toBeTruthy();
  const event = await (await org.get(`/api/events/${SHOWCASE}`)).json();
  const backup = await (await org.get(`/api/events/${event.id}/export.json`)).json();
  expect(backup.teams.every((t: { members: unknown[] }) => t.members.length > 0)).toBeTruthy();
  expect(backup.judges.length).toBe(4);

  await page.goto('/login');
  await page.getByLabel('Email').fill('alice@example.com');
  await page.getByLabel(/^Password/).fill('organizer-pass1');
  await page.locator('form').getByRole('button', { name: 'Log in' }).click();
  await expect(page).not.toHaveURL(/\/login/);
  await page.goto('/events');
  await page.getByLabel('Backup file').setInputFiles({
    name: 'showcase.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(backup)),
  });
  await expect(page.getByText(/4 judges/)).toBeVisible();
  const slug = `restored-${uid()}`;
  await page.getByLabel('New URL slug').fill(slug);
  await page.getByRole('button', { name: 'Import event' }).click();
  await expect(page).toHaveURL(new RegExp(`/events/${slug}$`));

  // The panel came across with its tracks, and the members with their teams.
  await page.goto(`/events/${slug}/results`);
  await expect(page.getByLabel('Track for Omar Judge')).toContainText('Developer Tools');
  await expect(page.getByLabel('Track for Sam Judge')).toContainText('Any track');
  const restored = await (await org.get(`/api/events/${slug}`)).json();
  const teams = await (await org.get(`/api/events/${restored.id}/export.json`)).json();
  expect(teams.teams.map((t: { members: { email: string }[] }) => t.members.map((m) => m.email))).toEqual(
    backup.teams.map((t: { members: { email: string }[] }) => t.members.map((m) => m.email)),
  );
  await org.dispose();
});
