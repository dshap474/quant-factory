/**
 * Stale-chunk detection and the one-reload-per-window recovery guard.
 *
 * USAGE:
 *   pnpm exec vitest run src/lib/chunk-reload.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it, vi } from 'vitest';

import { isChunkLoadError, reloadForStaleChunk, type StorageLike } from './chunk-reload';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function memoryStorage(): StorageLike {
  const map = new Map<string, string>();
  return {
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => {
      map.set(key, value);
    },
  };
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('isChunkLoadError', () => {
  it('matches the browser dynamic-import failure messages', () => {
    expect(
      isChunkLoadError(new TypeError('Failed to fetch dynamically imported module: /assets/a.js')),
    ).toBe(true);
    expect(isChunkLoadError(new Error('error loading dynamically imported module'))).toBe(true);
    expect(isChunkLoadError(new Error('Importing a module script failed.'))).toBe(true);
  });

  it('does not match unrelated errors', () => {
    expect(isChunkLoadError(new Error('Cannot read properties of undefined'))).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
    expect(isChunkLoadError({ message: 'Failed to fetch dynamically imported module' })).toBe(
      false,
    );
  });
});

describe('reloadForStaleChunk', () => {
  it('reloads on the first call', () => {
    const reload = vi.fn();
    const reloaded = reloadForStaleChunk({ storage: memoryStorage(), now: () => 1_000, reload });
    expect(reloaded).toBe(true);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('does not reload again inside the cooldown window', () => {
    const storage = memoryStorage();
    const reload = vi.fn();
    expect(reloadForStaleChunk({ storage, now: () => 1_000, reload })).toBe(true);
    expect(reloadForStaleChunk({ storage, now: () => 5_000, reload })).toBe(false);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('reloads again once the cooldown window has passed', () => {
    const storage = memoryStorage();
    const reload = vi.fn();
    expect(reloadForStaleChunk({ storage, now: () => 1_000, reload })).toBe(true);
    expect(reloadForStaleChunk({ storage, now: () => 12_000, reload })).toBe(true);
    expect(reload).toHaveBeenCalledTimes(2);
  });
});
