import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Kept separate from vite.config.ts so the production build never needs the test
// toolchain's types on its config path.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // Playwright owns tests/e2e; Vitest only runs the unit tests beside the source.
    include: ['src/**/*.test.{ts,tsx}'],
  },
});
