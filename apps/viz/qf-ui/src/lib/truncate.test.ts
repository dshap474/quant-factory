/**
 * Tests for middle truncation (truncateMiddle).
 *
 * USAGE:
 *   pnpm exec vitest run src/lib/truncate.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import { truncateMiddle } from './truncate';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('truncateMiddle', () => {
  it('keeps 8 leading and 6 trailing characters by default', () => {
    expect(truncateMiddle('0x8f3c2a91d04e7b55c1aa')).toBe('0x8f3c2a…55c1aa');
  });

  it('leaves values up to head + tail + 2 whole', () => {
    expect(truncateMiddle('0123456789abcdef')).toBe('0123456789abcdef');
    expect(truncateMiddle('0123456789abcdefg')).toBe('01234567…bcdefg');
  });

  it('honours custom lengths', () => {
    expect(truncateMiddle('20240101T000000Z-v003-example-rerun', { head: 13, tail: 10 })).toBe(
      '20240101T0000…mple-rerun',
    );
  });
});
