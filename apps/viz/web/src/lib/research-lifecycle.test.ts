/**
 * Research lifecycle tests: navigator versions sort newest first.
 *
 * USAGE:
 *   pnpm exec vitest run src/lib/research-lifecycle.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import { compareVersionsDesc } from './research-lifecycle';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('compareVersionsDesc', () => {
  it('orders newest memory version first', () => {
    const versions = [{ memory_version: 'v009' }, { memory_version: 'v010' }];
    expect(versions.sort(compareVersionsDesc).map((v) => v.memory_version)).toEqual([
      'v010',
      'v009',
    ]);
  });
});
