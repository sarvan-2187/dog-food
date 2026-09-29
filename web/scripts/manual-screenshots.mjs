// Regenerates every screenshot in USER-MANUAL.md from the running stack.
//
//   docker compose up        # fixture data, ideally a fresh volume
//   cd web && node scripts/manual-screenshots.mjs
//
// Idempotent enough to re-run: assignment only fills gaps, and the announcement
// and demo score are skipped if they already exist.
import { chromium } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const BASE = process.env.BASE_URL ?? 'http://localhost:8000';
const OUT = fileURLToPath(new URL('../../docs/screenshots/manual/', import.meta.url));
const ROLES = ['participant', 'judge', 'organizer', 'admin'];
const ACCOUNTS = {
  organizer: ['alice@example.com', 'organizer-pass1'],
  admin: ['priya@example.com', 'admin-pass123'],
  judge: ['sam@example.com', 'judge-pass123'],
  participant: ['jordan@example.com', 'participant-pass1'],
};

const browser = await chromium.launch();

async function session(role, { tour = false } = {}) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  if (!tour) {
    await context.addInitScript((roles) => {
      for (const r of roles) localStorage.setItem(`hackflow.tour.seen.${r}`, '1');
    }, ROLES);
  }
  if (role) {
    const [email, password] = ACCOUNTS[role];
    const r = await context.request.post(`${BASE}/api/auth/login`, { data: { email, password } });
    if (!r.ok()) throw new Error(`login ${role}: ${r.status()}`);
  }
  const page = await context.newPage();
  page.on('pageerror', (e) => console.log('PAGEERROR', String(e).slice(0, 200)));
  return { context, page, api: context.request };
}

async function open(page, path) {
  await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(700); // entrance transitions
}

async function shot(page, name, target) {
  const path = `${OUT}${name}.png`;
  if (target === 'full') {
    await page.screenshot({ path, fullPage: true });
  } else if (target) {
    await target.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    await target.screenshot({ path });
  } else {
    await page.screenshot({ path });
  }
  console.log('saved', name);
}

const card = (page, title) =>
  page.locator('section').filter({ has: page.getByRole('heading', { name: title, exact: true }) }).first();

async function json(res) {
  if (!res.ok()) throw new Error(`${res.url()} -> ${res.status()} ${await res.text()}`);
  return res.json();
}

// --- setup: the state a mid-event demo needs -------------------------------
const org = await session('organizer');
const dogfood = await json(await org.api.get(`${BASE}/api/events/dogfood-2026`));
const showcase = await json(await org.api.get(`${BASE}/api/events/judging-showcase-2026`));
await json(await org.api.post(`${BASE}/api/events/${showcase.id}/assignments`, { data: { judges_per_submission: 3 } }));
const posted = await json(await org.api.get(`${BASE}/api/events/${dogfood.id}/announcements`));
if (!posted.length) {
  await json(
    await org.api.post(`${BASE}/api/events/${dogfood.id}/announcements`, {
      data: {
        title: 'Demos start at 17:00 UTC on Sunday',
        body: 'Each team gets five minutes. Have your live demo link filled in on your submission before then.',
      },
    }),
  );
}

const judge = await session('judge');
const progress = await json(await judge.api.get(`${BASE}/api/judge/assignments`));
if (progress.pending.length && !progress.done.length) {
  const first = progress.pending[0];
  const sheet = await json(await judge.api.get(`${BASE}/api/assignments/${first.id}/sheet`));
  const values = Object.fromEntries(sheet.rubrics.flatMap((r) => r.criteria).map((c) => [c.key, Math.round((c.max_score ?? 10) * 0.8)]));
  await json(await judge.api.put(`${BASE}/api/assignments/${first.id}/score`, { data: { values, comment: 'Clear demo, solid tests.' } }));
}
const after = await json(await judge.api.get(`${BASE}/api/judge/assignments`));
// Any assignment shows the form; an unscored one just shows it empty.
const unscored = after.pending[0] ?? after.done[0];

// --- signed out -------------------------------------------------------------
{
  const { page, context } = await session(null);
  await open(page, '/login');
  await shot(page, '01-login');
  await open(page, '/register');
  await shot(page, '02-register');
  await open(page, '/forgot-password');
  await shot(page, '19-forgot-password');
  await context.close();
}

// --- guided tours -----------------------------------------------------------
for (const [role, first, second] of [
  ['participant', '03-tour-participant-welcome', '04-tour-participant-teams'],
  ['organizer', '10-tour-organizer', null],
  ['judge', '15-tour-judge', null],
]) {
  const { page, context } = await session(role, { tour: true });
  await open(page, '/dashboard');
  const popover = page.locator('.driver-popover');
  await popover.waitFor({ timeout: 5000 });
  await page.waitForTimeout(500);
  await shot(page, first);
  if (second) {
    for (let i = 0; i < 8 && !(await popover.innerText()).includes('Get on a team'); i++) {
      await page.locator('.driver-popover-next-btn').click();
      await page.waitForTimeout(600);
    }
    await shot(page, second);
  }
  await context.close();
}

// --- participant ------------------------------------------------------------
{
  const { page, context } = await session('participant');
  await open(page, '/events/dogfood-2026');
  await shot(page, '05-event-detail');
  await shot(page, '20-your-team', card(page, 'Your team'));
  await open(page, '/teams/mine');
  await shot(page, '06-my-teams');
  await open(page, '/teams/1/submission');
  await shot(page, '07-submission', 'full');
  await open(page, '/events/dogfood-2026/gallery');
  await shot(page, '08-gallery');
  await open(page, '/submissions/2');
  await shot(page, '18-submission-detail-voting', 'full');
  await open(page, '/profile');
  await shot(page, '09-profile');
  await context.close();
}

// --- judge ------------------------------------------------------------------
{
  const { page, context } = await session('judge');
  await open(page, '/judge');
  await shot(page, '14-judge-dashboard');
  if (unscored) {
    await open(page, `/assignments/${unscored.id}/score`);
    await shot(page, '16-score-form', 'full');
  }
  await context.close();
}

// --- organizer --------------------------------------------------------------
{
  const { page } = org;
  await open(page, '/dashboard');
  await shot(page, '25-help-someone-sign-in', card(page, 'Help someone sign in'));
  await open(page, '/events/new');
  await shot(page, '17-create-event');
  await open(page, '/events/dogfood-2026/settings');
  await shot(page, '11-event-settings');
  await open(page, '/events/dogfood-2026');
  await shot(page, '21-announcements', card(page, 'Announcements'));
  await open(page, '/events/judging-showcase-2026/rubric');
  await shot(page, '12-rubric-builder');
  await open(page, '/events/judging-showcase-2026/results');
  await shot(page, '13-assignments-results');
  await shot(page, '22-judging-progress', card(page, 'Judging progress'));
  await shot(page, '23-winners', card(page, 'Winners'));
  await open(page, '/events/dogfood-2026/results');
  await shot(page, '24-community-voting', card(page, 'Community voting'));
  await org.context.close();
}

// --- admin ------------------------------------------------------------------
{
  const { page, context } = await session('admin');
  await open(page, '/admin/users');
  await shot(page, '26-admin-users');
  await context.close();
}

await browser.close();
console.log('done');
