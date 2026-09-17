import { test, expect } from '@playwright/test';

/**
 * The single end-to-end lifecycle walk required by PLAN.md section 9. It doubles
 * as the demo-video script, so it follows the path a real participant takes
 * rather than poking endpoints.
 *
 * Phase 1 scope: sign-up -> team -> invite -> autosave draft -> submit -> gallery.
 * Phase 2 extends it with judge assignment, scoring and normalised results.
 */
const unique = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

test('participant lifecycle: sign up, form a team, draft, submit, appear in the gallery', async ({ page, browser }, testInfo) => {
  const stamp = unique();
  const founder = `founder-${stamp}@example.com`;
  const teammate = `mate-${stamp}@example.com`;
  const projectTitle = `Lifecycle Project ${stamp}`;

  // --- sign up -------------------------------------------------------------
  await page.goto('/register');
  await page.getByLabel('Name').fill('Lifecycle Founder');
  await page.getByLabel('Email').fill(founder);
  await page.getByLabel('Password').fill('supersecret1');
  await page.locator('form').getByRole('button', { name: 'Sign up' }).click();
  await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible();

  // --- open the seeded event ----------------------------------------------
  await page.getByRole('link', { name: 'Events' }).first().click();
  await page.getByText('Dogfood Hackathon 2026').click();
  // The deadline is on screen before anything is typed (PLAN.md 4.1).
  await expect(page.getByText(/remaining|Deadline passed/)).toBeVisible();

  // --- form a team ---------------------------------------------------------
  await page.getByRole('button', { name: 'Create a team' }).click();
  await page.getByLabel('Team name').fill(`Team ${stamp}`);
  await page.getByRole('button', { name: 'Create team' }).click();
  const inviteInput = page.getByLabel('Invite link');
  await expect(inviteInput).toBeVisible();
  const inviteUrl = await inviteInput.inputValue();
  expect(inviteUrl).toContain('/join/');

  // --- autosave a draft ----------------------------------------------------
  await page.getByRole('link', { name: 'Go to your submission' }).click();
  const title = page.getByLabel('Title');
  await title.fill(projectTitle);
  await title.blur();
  // The autosave indicator must confirm the write, not leave the user guessing.
  await expect(page.getByText('Saved')).toBeVisible();

  const description = page.getByLabel('Description');
  await description.fill('An end-to-end lifecycle walk used as the demo script.');
  await description.blur();
  await expect(page.getByText('Saved')).toBeVisible();

  // A reload proves the draft really persisted server-side.
  await page.reload();
  await expect(page.getByLabel('Title')).toHaveValue(projectTitle);

  // --- submit --------------------------------------------------------------
  await page.getByRole('button', { name: 'Submit for judging' }).click();
  await expect(page.getByText(/Submission sent for judging/)).toBeVisible();

  // --- it shows up in the public gallery, and search finds it --------------
  await page.getByRole('link', { name: 'Gallery' }).first().click();
  await expect(page.getByText(projectTitle)).toBeVisible();
  await page.getByLabel('Search').fill(projectTitle);
  await expect(page.getByText(projectTitle)).toBeVisible();
  await page.getByLabel('Search').fill('no-such-project-xyz');
  await expect(page.getByText('No matches')).toBeVisible();

  // --- a teammate redeems the invite and lands on an explicit success screen
  // A separate context, so the teammate has their own session cookie. baseURL is
  // passed through explicitly because browser.newContext() does not inherit the
  // `use` block's options.
  const mateContext = await browser.newContext({ baseURL: testInfo.project.use.baseURL });
  const mate = await mateContext.newPage();
  await mate.goto('/register');
  await mate.getByLabel('Name').fill('Lifecycle Mate');
  await mate.getByLabel('Email').fill(teammate);
  await mate.getByLabel('Password').fill('supersecret1');
  await mate.locator('form').getByRole('button', { name: 'Sign up' }).click();
  // Wait for the session to exist before redeeming, or the invite POST races the
  // sign-up and arrives unauthenticated.
  await expect(mate.getByRole('button', { name: 'Log out' })).toBeVisible();
  await mate.goto(inviteUrl);
  await expect(mate.getByText("You're in")).toBeVisible();
  await expect(mate.getByText(/2 members/)).toBeVisible();

  // Following the same invite again is a normal thing to do, not an error screen.
  await mate.goto(inviteUrl);
  await expect(mate.getByText(/already on this team/i)).toBeVisible();
  await mateContext.close();
});
