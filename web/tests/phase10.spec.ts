import { expect, test } from '@playwright/test';
import type { APIRequestContext, Page } from '@playwright/test';

/**
 * PLAN.md Phase 10, end to end in a real browser. Every test brings its own
 * accounts and restores anything shared it changes, so specs can run in
 * parallel and be repeated against the same stack.
 */

const SHOWCASE = 'judging-showcase-2026'; // seeded past its deadline: judgeable
const OPEN_EVENT = 'dogfood-2026'; // seeded still open for submissions

const uid = () => `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;

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

async function freshParticipant(request: APIRequestContext, name = 'Pat Phase') {
  const email = `p10-${uid()}@example.com`;
  const r = await request.post('/api/auth/register', { data: { email, password: 'phase-ten-pass', name } });
  expect(r.ok()).toBeTruthy();
  await request.post('/api/auth/logout');
  return email;
}

test.beforeEach(({ page }) => {
  // Every destructive step asks first (window.confirm); these flows mean "yes".
  page.on('dialog', (d) => d.accept());
});

test('10.5 - a team adds project links, with bad ones caught inline', async ({ page, request }) => {
  const email = await freshParticipant(request);
  await login(page, email, 'phase-ten-pass');
  await page.goto(`/events/${OPEN_EVENT}`);
  await page.getByLabel('Team name').fill(`Links ${uid()}`.slice(0, 30));
  await page.getByRole('button', { name: 'Create team' }).click();
  await page.getByRole('link', { name: 'Go to your submission' }).click();

  const repo = page.getByLabel('Code repository');
  await repo.fill('javascript:alert(1)');
  await expect(page.getByText('Enter a full web address starting with https://')).toBeVisible();
  await repo.fill('https://github.com/example/linked');
  const saved = page.waitForResponse((r) => r.url().endsWith('/submission') && r.request().method() === 'PATCH');
  await repo.blur();
  expect((await saved).ok()).toBeTruthy();
  await page.reload();
  await expect(page.getByLabel('Code repository')).toHaveValue('https://github.com/example/linked');
});

test('10.5 / 10.7 - a judge sees the links, and can step back from a conflict', async ({
  page,
  playwright,
  baseURL,
  request,
}) => {
  // Its own event from start to finish, so this never races the specs that
  // judge the shared showcase event.
  const org = await apiAs(playwright, baseURL, 'alice@example.com', 'organizer-pass1');
  const slug = `conflict-${uid()}`;
  const now = Date.now();
  const event = await (
    await org.post('/api/events', {
      data: {
        slug,
        name: `Conflict ${slug}`.slice(0, 60),
        start_at: new Date(now - 3_600_000).toISOString(),
        end_at: new Date(now + 86_400_000).toISOString(),
      },
    })
  ).json();
  await org.post(`/api/events/${event.id}/publish`);
  await org.post(`/api/events/${event.id}/rubrics`, {
    data: { name: 'Only Rubric', criteria: [{ key: 'impact', label: 'Impact', weight: 1, max_score: 10 }] },
  });

  const entrantEmail = await freshParticipant(request, 'Entrant');
  const entrant = await apiAs(playwright, baseURL, entrantEmail, 'phase-ten-pass');
  const team = await (await entrant.post(`/api/events/${event.id}/teams`, { data: { name: 'Pager Team' } })).json();
  await entrant.patch(`/api/teams/${team.id}/submission`, {
    data: {
      title: 'Pager Triage',
      description: 'Groups related alerts into one incident.',
      repo_url: 'https://github.com/example/pager-triage',
      demo_url: 'https://pager-triage.example.com',
    },
  });
  expect((await entrant.post(`/api/teams/${team.id}/submission/submit`)).ok()).toBeTruthy();
  await org.patch(`/api/events/${event.id}`, { data: { end_at: new Date().toISOString() } }); // close submissions

  const invite = await (await org.post('/api/judge-invites', { data: { event_id: event.id } })).json();
  const judgeEmail = await freshParticipant(request, 'Jo Judge');
  const judge = await apiAs(playwright, baseURL, judgeEmail, 'phase-ten-pass');
  expect((await judge.post(`/api/judge-invites/${invite.token}/redeem`)).ok()).toBeTruthy();
  expect((await org.post(`/api/events/${event.id}/assignments`, { data: { judges_per_submission: 1 } })).ok()).toBeTruthy();
  const mine = await (await judge.get('/api/judge/assignments')).json();
  const pager = mine.pending.find((a: { submission_title: string }) => a.submission_title === 'Pager Triage');
  expect(pager).toBeTruthy();

  await login(page, judgeEmail, 'phase-ten-pass');
  await page.goto(`/assignments/${pager.id}/score`);
  await expect(page.getByRole('link', { name: /^Code/ })).toHaveAttribute('href', 'https://github.com/example/pager-triage');
  await expect(page.getByRole('link', { name: /^Live demo/ })).toBeVisible();

  await page.getByRole('button', { name: 'I have a conflict of interest with this project' }).click();
  await page.getByLabel(/^Reason/).fill('I mentored this team');
  await page.getByRole('button', { name: 'Step back from this project' }).click();
  await expect(page).toHaveURL(/\/judge$/);

  await page.context().clearCookies();
  await login(page, 'alice@example.com', 'organizer-pass1');
  await page.goto(`/events/${slug}/results`);
  const card = page.locator('[data-tour="judging-progress"]');
  const row = card.locator('li', { hasText: judgeEmail });
  await expect(row.getByText(/Declared a conflict with/)).toContainText('Pager Triage');
  await org.dispose();
  await judge.dispose();
  await entrant.dispose();
});

test('10.6 - a winner is chosen, and appears only once results are revealed', async ({ page, playwright, baseURL }) => {
  const org = await apiAs(playwright, baseURL, 'alice@example.com', 'organizer-pass1');
  const event = await (await org.get(`/api/events/${SHOWCASE}`)).json();
  const hiddenUntil = event.results_hidden_until;

  try {
    await login(page, 'alice@example.com', 'organizer-pass1');
    await page.goto(`/events/${SHOWCASE}/results`);
    const picker = page.locator('[data-tour="winners"]').getByLabel('Winner of 1st Place');
    const value = await picker.locator('option', { hasText: 'Green Main' }).getAttribute('value');
    await picker.selectOption(value!);
    await expect(page.getByText('1st Place saved.')).toBeVisible();

    // Hidden: a visitor is told nothing.
    const visitor = await playwright.request.newContext({ baseURL });
    expect((await (await visitor.get(`/api/events/${event.id}/winners`)).json()).visible).toBe(false);

    // Revealed: the winner appears on the public event page.
    await org.patch(`/api/events/${event.id}`, {
      data: { results_hidden_until: new Date(Date.now() - 60_000).toISOString() },
    });
    await page.context().clearCookies();
    await page.goto(`/events/${SHOWCASE}`);
    const winnerCard = page.locator('li', { has: page.getByText('1st Place', { exact: true }) });
    await expect(winnerCard.getByRole('link', { name: 'Green Main' })).toBeVisible();
    await visitor.dispose();
  } finally {
    await org.patch(`/api/events/${event.id}`, { data: { results_hidden_until: hiddenUntil } });
    await org.put(`/api/events/${event.id}/awards`, { data: { prize_rank: '1st Place', submission_id: null } });
    await org.dispose();
  }
});

test('10.11 - an announcement reaches participants on their dashboard', async ({ page, playwright, baseURL, request }) => {
  const email = await freshParticipant(request);
  const me = await apiAs(playwright, baseURL, email, 'phase-ten-pass');
  const event = await (await me.get(`/api/events/${OPEN_EVENT}`)).json();
  expect((await me.post(`/api/events/${event.id}/teams`, { data: { name: `News ${uid()}`.slice(0, 30) } })).ok()).toBeTruthy();

  const title = `Demos at 5 (${uid()})`;
  const org = await apiAs(playwright, baseURL, 'alice@example.com', 'organizer-pass1');
  try {
    await login(page, 'alice@example.com', 'organizer-pass1');
    await page.goto(`/events/${OPEN_EVENT}`);
    const card = page.locator('[data-tour="announcements"]');
    await card.getByLabel('Title').fill(title);
    await card.getByLabel('Message').fill('Livestream link to follow.');
    await card.getByRole('button', { name: 'Post announcement' }).click();
    await expect(card.getByText('Posted.')).toBeVisible();

    await page.context().clearCookies();
    await login(page, email, 'phase-ten-pass');
    await page.goto('/dashboard');
    await expect(page.getByText(title)).toBeVisible();
  } finally {
    // It would otherwise sit on every other participant's dashboard too.
    const list = await (await org.get(`/api/events/${event.id}/announcements`)).json();
    for (const a of list.filter((x: { title: string }) => x.title === title)) {
      await org.delete(`/api/events/${event.id}/announcements/${a.id}`);
    }
    await org.dispose();
    await me.dispose();
  }
});

test('10.9 - a participant can leave their team', async ({ page, request }) => {
  const email = await freshParticipant(request);
  await login(page, email, 'phase-ten-pass');
  await page.goto(`/events/${OPEN_EVENT}`);
  await page.getByLabel('Team name').fill(`Leavers ${uid()}`.slice(0, 30));
  await page.getByRole('button', { name: 'Create team' }).click();
  await expect(page.getByText('Captain', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Leave team' }).click();
  await expect(page.getByRole('button', { name: 'Create a team' })).toBeVisible();
});

test('10.12 - a new event is a draft until the organizer publishes it', async ({ page, playwright, baseURL }) => {
  const slug = `draft-${uid()}`;
  const org = await apiAs(playwright, baseURL, 'alice@example.com', 'organizer-pass1');
  const created = await (
    await org.post('/api/events', {
      data: { slug, name: `Draft ${slug}`.slice(0, 60), start_at: '2031-01-01T09:00:00Z', end_at: '2031-01-02T18:00:00Z' },
    })
  ).json();
  expect(created.status).toBe('draft');

  const visitor = await playwright.request.newContext({ baseURL });
  try {
    expect((await visitor.get(`/api/events/${slug}`)).status()).toBe(404);

    await login(page, 'alice@example.com', 'organizer-pass1');
    await page.goto(`/events/${slug}/settings`);
    await page.getByRole('button', { name: 'Publish event' }).click();
    await expect(page.getByText('Published - participants can see it now.')).toBeVisible();
    expect((await visitor.get(`/api/events/${slug}`)).status()).toBe(200);
  } finally {
    await org.delete(`/api/events/${created.id}`); // no teams, so deletable
    await visitor.dispose();
    await org.dispose();
  }
});

test('10.10 - an admin can make someone an organizer', async ({ page, request }) => {
  const email = await freshParticipant(request, 'Future Organizer');
  await login(page, 'priya@example.com', 'admin-pass123');
  await page.getByRole('link', { name: 'Users' }).click();
  await page.getByLabel('Search by name or email').fill(email);
  await page.getByLabel('Search by name or email').press('Enter');
  // Scope to this test's own (unique) account - earlier runs leave other "Future Organizer"s behind.
  const row = page.locator('li', { hasText: email });
  await row.getByLabel('Role for Future Organizer').selectOption('organizer');
  await expect(page.getByText('Future Organizer updated.')).toBeVisible();

  await page.context().clearCookies();
  await login(page, email, 'phase-ten-pass');
  await expect(page.locator('[data-tour="nav-create-event"]')).toBeVisible();
});
