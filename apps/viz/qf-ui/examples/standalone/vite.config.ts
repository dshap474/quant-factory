/**
 * Vite config for the qf-ui standalone example: a consumer app that reaches the kit
 * only through `@quant-factory/qf-ui` package exports (package self-reference), with
 * Tailwind v4 and React as a host would set them up.
 *
 * USAGE (from apps/viz/qf-ui):
 *   pnpm run example:build    # vite build into examples/standalone/dist
 *   pnpm run example:check    # typecheck + build
 *   pnpm exec vite preview --config examples/standalone/vite.config.ts --port 4190
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { fileURLToPath } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// --------------------------------------------------------------------------- #
// Config
// --------------------------------------------------------------------------- #

export default defineConfig({
  root: fileURLToPath(new URL('.', import.meta.url)),
  plugins: [tailwindcss(), react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
