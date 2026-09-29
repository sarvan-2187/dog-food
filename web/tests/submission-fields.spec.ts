import { expect, test } from '@playwright/test';
import type { APIRequestContext, Page } from '@playwright/test';

/**
 * The full T1 submission field set, end to end: tagline and tech tags, an image
 * gallery of up to five, organizer-defined custom questions, and the gallery's
 * track and tech-tag filters. Every test brings its own accounts (and, where it
 * changes event settings, its own event), so specs can run in parallel.
 */

const OPEN_EVENT = 'dogfood-2026'; // seeded still open for submissions

const uid = () => `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;

// A real 1x1 PNG: the server checks the file's magic bytes, not just its name.
const PNG_1PX = Buffer.from(
  '89504e470d0a1a0a0000000d494844440000000100000001080600000' +
    '01f15c4890000000a49444154789c6360000002000155e28f760000000049454e44ae426082',
  'hex',
);

type Playwright = { request: { newContext: (o: { baseURL?: string }) => Promise<APIRequestContext> } };

async function login(page: Page, email: string, password: string) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel(/^Password/).fill(password);
  await page.locator('form').getByRole('button', { name: 'Log in' }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

async function apiAs(playwright: Playwright, baseURL: string | undefined, email: string, password: string) {
  const ctx = await playwright.request.newContext({ baseURL });
  const r = await ctx.post('/api/auth/login', { data: { email, password } });
  expect(r.ok()).toBeTruthy();
  return ctx;
}

async function freshParticipant(request: APIRequestContext, name = 'Tess Fields') {
  const email = `t1-${uid()}@example.com`;
  const r = await request.post('/api/auth/register', { data: { email, password: 'fields-pass-1', name } });
  expect(r.ok()).toBeTruthy();
  await request.post('/api/auth/logout');
  return email;
}

/** A published event of this test's own, open for submissions. */
async function ownEvent(org: APIRequestContext) {
  const slug = `fields-${uid()}`;
  const now = Date.now();
  const event = await (
    await org.post('/api/events', {
      data: {
        slug,
        name: `Fields ${slug}`.slice(0, 60),
        start_at: new Date(now - 3_600_000).toISOString(),
        end_at: new Date(now + 86_400_000).toISOString(),
        tracks: ['Tools', 'Apps'],
      },
    })
  ).json();
  await org.post(`/api/events/${event.id}/publish`);
  return event as { id: number; slug: string };
}

test.beforeEach(({ page }) => {
  page.on('dialog', (d) => d.accept());
});

test('a team adds a tagline, tech tags and an ordered image gallery', async ({ page, request }) => {
  const email = await freshParticipant(request);
  await login(page, email, 'fields-pass-1');
  await page.goto(`/events/${OPEN_EVENT}`);
  await page.getByLabel('Team name').fill(`Fields ${uid()}`.slice(0, 30));
  await page.getByRole('button', { name: 'Create team' }).click();
  await page.getByRole('link', { name: 'Go to your submission' }).click();

  const saved = () => page.waitForResponse((r) => r.url().endsWith('/submission') && r.request().method() === 'PATCH');
  await page.getByLabel('Title').fill('Gallery Test');
  let save = saved();
  await page.getByLabel('Title').blur();
  await save;
  await page.getByLabel('Tagline').fill('One line that sells it');
  save = saved();
  await page.getByLabel('Tagline').blur();
  expect((await save).ok()).toBeTruthy();
  await page.getByLabel('Tech tags').fill('Rust, cli, rust');
  save = saved();
  await page.getByLabel('Tech tags').blur();
  expect((await save).ok()).toBeTruthy();
  // The server deduplicates case-insensitively, and the field shows what it kept.
  await expect(page.getByLabel('Tech tags')).toHaveValue('Rust, cli');

  await page.reload();
  // Images appear once the draft exists.
  for (const name of ['one.png', 'two.png']) {
    const upload = page.waitForResponse((r) => r.url().endsWith('/submission/images') && r.ok());
    await page.getByLabel('Choose an image to add').setInputFiles({ name, mimeType: 'image/png', buffer: PNG_1PX });
    await upload;
  }
  const list = page.getByRole('list', { name: 'Project images, in order' });
  await expect(list.getByRole('listitem')).toHaveCount(2);
  await expect(list.getByRole('listitem').first().getByText('Thumbnail')).toBeVisible();
  const firstSrc = await list.getByRole('img', { name: 'Image 1' }).getAttribute('src');

  await page.getByRole('button', { name: 'Move image 2 earlier' }).click();
  await expect(list.getByRole('img', { name: 'Image 2' })).toHaveAttribute('src', firstSrc!);

  await page.getByRole('button', { name: 'Remove image 2' }).click();
  await expect(list.getByRole('listitem')).toHaveCount(1);

  await page.reload();
  await expect(page.getByLabel('Tagline')).toHaveValue('One line that sells it');
  await expect(page.getByRole('list', { name: 'Project images, in order' }).getByRole('listitem')).toHaveCount(1);
});

test('custom questions: required ones block Submit, judges and the public see what they should', async ({
  page,
  playwright,
  baseURL,
  request,
}) => {
  const org = await apiAs(playwright, baseURL, 'alice@example.com', 'organizer-pass1');
  const event = await ownEvent(org);

  // The organizer defines the questions in Event settings.
  await login(page, 'alice@example.com', 'organizer-pass1');
  await page.goto(`/events/${event.slug}/settings`);
  await page.getByRole('button', { name: 'Add question' }).click();
  await page.getByLabel('Question', { exact: true }).fill('Who is it for?');
  await page.getByLabel('Required').check();
  await page.getByLabel('Show publicly on the project page').check();
  await page.getByRole('button', { name: 'Add question' }).click();
  await page.getByLabel('Question', { exact: true }).nth(1).fill('What went wrong?');
  await page.getByRole('button', { name: 'Save questions' }).click();
  await expect(page.getByText('Questions saved.')).toBeVisible();

  // A team answers on the submission form.
  const email = await freshParticipant(request);
  const entrant = await apiAs(playwright, baseURL, email, 'fields-pass-1');
  const team = await (await entrant.post(`/api/events/${event.id}/teams`, { data: { name: 'Askers' } })).json();
  await entrant.patch(`/api/teams/${team.id}/submission`, { data: { title: 'Asked', description: 'Answers questions.' } });
  await page.context().clearCookies();
  await login(page, email, 'fields-pass-1');
  await page.goto(`/teams/${team.id}/submission`);
  await expect(page.getByText('(required to submit)')).toBeVisible();

  await page.getByRole('button', { name: 'Submit for judging' }).click();
  await expect(page.getByText(/Answer every required question before submitting: Who is it for\?/)).toBeVisible();

  const answer = page.getByLabel(/Who is it for\?/);
  await answer.fill('On-call engineers');
  const saved = page.waitForResponse((r) => r.url().endsWith('/submission') && r.request().method() === 'PATCH');
  await answer.blur();
  expect((await saved).ok()).toBeTruthy();
  await page.getByLabel('What went wrong?').fill('Nothing to see here');
  const saved2 = page.waitForResponse((r) => r.url().endsWith('/submission') && r.request().method() === 'PATCH');
  await page.getByLabel('What went wrong?').blur();
  await saved2;
  await page.getByRole('button', { name: 'Submit for judging' }).click();
  await expect(page.getByText(/Submission sent for judging/)).toBeVisible();

  // The public project page shows only the answer the organizer made public.
  const sub = await (await entrant.get(`/api/teams/${team.id}/submission`)).json();
  await page.context().clearCookies();
  await page.goto(`/submissions/${sub.id}`);
  await expect(page.getByText('On-call engineers')).toBeVisible();
  await expect(page.getByText('Nothing to see here')).toHaveCount(0);

  // A judge sees every answer, read-only, on the score sheet.
  await org.post(`/api/events/${event.id}/rubrics`, {
    data: { name: 'Only Rubric', criteria: [{ key: 'impact', label: 'Impact', weight: 1, max_score: 10 }] },
  });
  await org.patch(`/api/events/${event.id}`, { data: { end_at: new Date().toISOString() } });
  const invite = await (await org.post('/api/judge-invites', { data: { event_id: event.id } })).json();
  const judgeEmail = await freshParticipant(request, 'Jude Fields');
  const judge = await apiAs(playwright, baseURL, judgeEmail, 'fields-pass-1');
  expect((await judge.post(`/api/judge-invites/${invite.token}/redeem`)).ok()).toBeTruthy();
  expect((await org.post(`/api/events/${event.id}/assignments`, { data: { judges_per_submission: 1 } })).ok()).toBeTruthy();
  const mine = await (await judge.get('/api/judge/assignments')).json();
  await login(page, judgeEmail, 'fields-pass-1');
  await page.goto(`/assignments/${mine.pending[0].id}/score`);
  const answers = page.getByRole('region', { name: "The team's answers to the organizers' questions" });
  await expect(answers.getByText('On-call engineers')).toBeVisible();
  await expect(answers.getByText('Nothing to see here')).toBeVisible();

  await org.dispose();
  await entrant.dispose();
  await judge.dispose();
});

test('the gallery shows taglines and tags, and filters by track and tag on the server', async ({ page }) => {
  await page.goto(`/events/${OPEN_EVENT}/gallery`);
  const flake = page.locator('section', { has: page.getByRole('heading', { name: 'Flake Finder' }) });
  await expect(page.getByText('Finds the flaky tests before they find you.')).toBeVisible();

  const byTag = page.waitForResponse((r) => r.url().includes('/api/gallery?') && r.url().includes('tag=pytest'));
  await page.getByRole('combobox', { name: 'Tech tag' }).click();
  await page.getByRole('option', { name: 'pytest' }).click();
  await byTag;
  await expect(page.getByRole('heading', { name: 'Flake Finder' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Standup Digest' })).toHaveCount(0);
  await expect(flake.getByLabel('Tech tags')).toContainText('pytest');

  await page.getByRole('combobox', { name: 'Tech tag' }).click();
  await page.getByRole('option', { name: 'All tags' }).click();
  const byTrack = page.waitForResponse((r) => r.url().includes('/api/gallery?') && r.url().includes('track=Productivity'));
  await page.getByRole('combobox', { name: 'Track' }).click();
  await page.getByRole('option', { name: 'Productivity' }).click();
  await byTrack;
  await expect(page.getByRole('heading', { name: 'Standup Digest' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Flake Finder' })).toHaveCount(0);
});
