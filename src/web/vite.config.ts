import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    // Dev only. In the container the API serves the built SPA directly.
    proxy: { '/api': 'http://localhost:8000', '/healthz': 'http://localhost:8000' },
  },
});
