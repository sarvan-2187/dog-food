import { defineConfig } from '@playwright/test';
import { tourSuppressed } from './tests/tour-state';

// Points at the running `docker compose` stack, the same way a judge would.
const baseURL = process.env.BASE_URL ?? 'http://localhost:8000';

export default defineConfig({
  testDir: './tests',
  use: { baseURL, storageState: tourSuppressed(baseURL) },
  reporter: [['list']],
  fullyParallel: true,
});
