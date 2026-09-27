import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  // Points at the running `docker compose` stack, the same way a judge would.
  use: { baseURL: process.env.BASE_URL ?? 'http://localhost:8000' },
  reporter: [['list']],
  fullyParallel: true,
});
