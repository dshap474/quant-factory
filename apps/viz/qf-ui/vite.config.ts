/**
 * Library build and test configuration for qf-ui (design system + charts).
 *
 * USAGE:
 *   pnpm build
 *   pnpm test
 *   pnpm exec vitest run --project charts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// --------------------------------------------------------------------------- #
// Configuration
// --------------------------------------------------------------------------- #

export default defineConfig({
  plugins: [react()],
  build: {
    lib: {
      entry: {
        index: 'src/index.ts',
        command: 'src/command/index.ts',
        tables: 'src/tables/index.ts',
        'tables-core': 'src/tables/core/index.ts',
        charts: 'src/charts/index.ts',
        'charts-core': 'src/charts/core/index.ts',
        'charts-geometry': 'src/charts/core/geometry.ts',
        'charts-renderers': 'src/charts/charts/index.ts',
        'charts-chrome': 'src/charts/components/index.ts',
        'charts-hooks': 'src/charts/hooks/index.ts',
        'charts-theme': 'src/charts/theme/index.ts',
      },
      formats: ['es'],
    },
    rollupOptions: {
      external: ['react', 'react-dom', 'react/jsx-runtime'],
    },
  },
  test: {
    projects: [
      {
        extends: true,
        test: {
          name: 'ui',
          environment: 'node',
          globals: false,
          include: ['src/**/*.test.{ts,tsx}'],
          exclude: ['src/charts/**'],
          setupFiles: ['./tests/setup-ui.ts'],
        },
      },
      {
        extends: true,
        test: {
          name: 'charts',
          environment: 'jsdom',
          globals: true,
          include: ['tests/charts/**/*.test.{ts,tsx}'],
          setupFiles: ['./tests/setup-charts.ts'],
        },
      },
    ],
  },
});
