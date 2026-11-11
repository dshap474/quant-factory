/**
 * ESLint correctness config for the React viz SPA.
 *
 * USAGE:
 *   pnpm exec eslint .
 *   pnpm run lint   # eslint + biome
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

// --------------------------------------------------------------------------- #
// Config
// --------------------------------------------------------------------------- #

export default tseslint.config(
  {
    ignores: ['dist/**', 'node_modules/**', 'src/lib/api/generated/**', '.dev/**', '_archive/**'],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    plugins: {
      'react-hooks': reactHooks,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      '@typescript-eslint/no-unused-vars': [
        'error',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
        },
      ],
    },
  },
  {
    files: ['scripts/**/*.{js,mjs,cjs}', 'vite.config.ts', 'vitest.config.ts', 'eslint.config.js'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: {
        ...globals.node,
      },
    },
  },
);
