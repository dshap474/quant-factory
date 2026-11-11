/**
 * Vitest config for the React viz SPA unit/component tests.
 *
 * USAGE:
 *   pnpm test
 *   pnpm exec vitest run
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import path from 'node:path';
import { defineConfig } from 'vitest/config';

// --------------------------------------------------------------------------- #
// Config
// --------------------------------------------------------------------------- #

export default defineConfig({
  esbuild: {
    jsx: 'automatic',
  },
  server: {
    fs: {
      allow: [path.resolve(__dirname, '..')],
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  test: {
    environment: 'node',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}', '../extensions/**/*.test.{ts,tsx}'],
    exclude: ['../extensions/node_modules/**', '../extensions/_archive/**'],
    globals: false,
  },
});
