/**
 * Pins the shared icon geometry constants.
 *
 * USAGE:
 *   pnpm exec vitest run src/lib/icon.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import { ICON_SIZE, ICON_SIZE_SM, ICON_STROKE } from './icon';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('icon constants', () => {
  it('fixes one size, one small size and one stroke', () => {
    expect(ICON_SIZE).toBe(16);
    expect(ICON_SIZE_SM).toBe(14);
    expect(ICON_STROKE).toBe(1.5);
  });
});
