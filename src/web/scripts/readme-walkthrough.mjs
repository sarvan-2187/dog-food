// Captures the README's ten-stage walkthrough (Registration -> Archive) from the
// running stack, one screenshot per stage, into docs/screenshots/walkthrough/.
//
//   docker compose up        # fixture data
//   cd web && node scripts/readme-walkthrough.mjs
//
// Sets up what a finished event needs to show (stages, prizes and winners on
// sample-hack-2026, judge assignment on judging-showcase-2026) through the API,
// and is safe to re-run. BASE_URL overrides the address.
import { chromium } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const BASE = process.env.BASE_URL ?? 'http://localhost:8000';
const OUT = fileURLToPath(new URL('../../docs/screenshots/walkthrough/', import.meta.url));
mkdirSync(OUT, { recursive: true });
const ROLES = ['participant', 'judge', 'organizer', 'admin'];
const ACCOUNTS = {
  organizer: ['alice@example.com', 'organizer-pass1'],
  judge: ['sam@example.com', 'judge-pass123'],
  participant: ['jordan@example.com', 'participant-pass1'],
};

const browser = await chromium.launch();

async function session(role, viewport = { width: 1280, height: 800 }) {
  const context = await browser.newContext({ viewport });
  await context.addInitScript((roles) => {
    for (const r of roles) localStorage.setItem(`hackflow.tour.seen.${r}`, '1');
  }, ROLES);
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
  await page.waitForTimeout(700);
}

const STATIC_BAR = 'header, aside { position: static !important; }';

async function shot(page, name, target) {
  const path = `${OUT}${name}.png`;
  if (target) {
    await target.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    // A card taller than the viewport is stitched while scrolling; unstick the top bar so it
    // isn't painted across the middle of the image.
    await target.screenshot({ path, style: STATIC_BAR });
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

// --- setup -----------------------------------------------------------------
const org = await session('organizer');
const get = async (slug) => json(await org.api.get(`${BASE}/api/events/${slug}`));
const dogfood = await get('dogfood-2026');
const showcase = await get('judging-showcase-2026');
const sample = await get('sample-hack-2026');

if (!dogfood.stages?.length) {
  const reveal = dogfood.results_hidden_until ?? dogfood.end_at;
  await json(
    await org.api.patch(`${BASE}/api/events/${dogfood.id}`, {
      data: {
        stages: [
          { name: 'Registration & team formation', description: 'Sign up and create or join a team.', starts_at: '2026-10-01T09:00:00Z', ends_at: dogfood.start_at },
          { name: 'Build sprint', description: 'Drafts autosave; submit before the deadline.', starts_at: dogfood.start_at, ends_at: dogfood.end_at },
          { name: 'Judging', description: 'Three judges score each project.', starts_at: dogfood.end_at, ends_at: reveal },
          { name: 'Results & certificates', description: 'Winners and certificates go live.', starts_at: reveal, ends_at: '2026-10-24T20:00:00Z' },
        ],
      },
    }),
  );
}
await json(await org.api.post(`${BASE}/api/events/${showcase.id}/assignments`, { data: { judges_per_submission: 3 } }));
if (!sample.prize_config?.prizes?.length) {
  await json(
    await org.api.patch(`${BASE}/api/events/${sample.id}`, {
      data: {
        prize_config: {
          prizes: [
            { rank: '1st Place', reward: '$1,200' },
            { rank: '2nd Place', reward: '$600' },
            { rank: '3rd Place', reward: '$300' },
          ],
        },
      },
    }),
  );
}
const awards = await json(await org.api.get(`${BASE}/api/events/${sample.id}/awards`));
for (const slot of awards.prizes) {
  if (!slot.submission_id && slot.suggested_submission_id) {
    await json(
      await org.api.put(`${BASE}/api/events/${sample.id}/awards`, {
        data: { prize_rank: slot.prize_rank, submission_id: slot.suggested_submission_id },
      }),
    );
  }
}
const winner = (await json(await org.api.get(`${BASE}/api/events/${sample.id}/awards`))).prizes[0].submission_id;

// --- 1 Registration ----------------------------------------------------------
{
  const { page, context } = await session(null);
  await open(page, '/register');
  await shot(page, '01-registration');
  await context.close();
}

// --- 2 Teams, 3 Submissions (participant) -----------------------------------
{
  const { page, context } = await session('participant');
  await open(page, '/events/dogfood-2026');
  await shot(page, '00-event-stages', card(page, 'Stages'));
  await shot(page, '02-team-formation', card(page, 'Your team'));
  await open(page, '/teams/1/submission');
  await shot(page, '03-submission');
  await context.close();
}

// --- 4 Eligibility, 5 Assignment (organizer) --------------------------------
await open(org.page, '/events/judging-showcase-2026/results');
await shot(org.page, '04-eligibility', card(org.page, 'Eligibility'));
await shot(org.page, '05-judge-assignment', card(org.page, 'Judging progress'));

// --- 6 Scoring (judge) -------------------------------------------------------
{
  const { page, context } = await session('judge');
  const progress = await json(await page.request.get(`${BASE}/api/judge/assignments`));
  const next = progress.pending[0] ?? progress.done[0];
  await open(page, `/assignments/${next.id}/score`);
  await page.getByText('Technical Rubric', { exact: true }).scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollBy(0, -120));
  await page.waitForTimeout(300);
  await shot(page, '06-scoring');
  await context.close();
}

// --- 7 Normalization, 8 Results --------------------------------------------
await open(org.page, '/events/sample-hack-2026/results');
await shot(org.page, '07-normalization', card(org.page, 'Normalised standings'));
{
  const { page, context } = await session('participant');
  await open(page, '/events/sample-hack-2026');
  await shot(page, '08-results', card(page, 'Winners'));

  // --- 9 Certificates: the organizer's copy, then the public check ---------
  const pdf = await org.api.get(`${BASE}/api/submissions/${winner}/certificate.pdf`);
  writeFileSync(`${OUT}certificate.pdf`, await pdf.body());
  console.log('saved certificate.pdf (rasterise with pdftoppm; pass SERIAL=... to shoot /verify)');
  if (process.env.SERIAL) {
    await open(page, `/verify/${process.env.SERIAL}`);
    await shot(page, '09-certificate-verify');
  }

  // --- 10 Archive ------------------------------------------------------------
  await open(page, '/events');
  await page.getByRole('tab', { name: /Past events/ }).click();
  await page.getByLabel('Search events').fill('Sample Hack');
  await page.waitForTimeout(500);
  await shot(page, '10-archive');
  await context.close();
}
await open(org.page, '/events/sample-hack-2026/settings');
await shot(org.page, '10-archive-backup', card(org.page, 'Backup'));
await open(org.page, '/integrations');
await shot(org.page, '11-integrations');
await org.context.close();

await browser.close();
console.log('done');
