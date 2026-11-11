/**
 * Persistence tests for app settings.
 *
 * USAGE:
 *   pnpm exec vitest run src/lib/shared/lib/app-settings.test.ts
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { afterEach, describe, expect, it } from 'vitest';

import {
  persistPreviewPageSize,
  persistSidebarCollapsed,
  readPreviewPageSize,
  readSidebarCollapsed,
} from './app-settings';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

afterEach(() => {
  localStorage.clear();
});

describe('sidebar collapse persistence', () => {
  it('defaults to collapsed and ignores unknown values', () => {
    expect(readSidebarCollapsed()).toBe(true);
    localStorage.setItem('qf-viz-sidebar-collapsed', 'maybe');
    expect(readSidebarCollapsed()).toBe(true);
  });

  it('round-trips both states', () => {
    persistSidebarCollapsed(false);
    expect(localStorage.getItem('qf-viz-sidebar-collapsed')).toBe('0');
    expect(readSidebarCollapsed()).toBe(false);
    persistSidebarCollapsed(true);
    expect(localStorage.getItem('qf-viz-sidebar-collapsed')).toBe('1');
    expect(readSidebarCollapsed()).toBe(true);
  });
});

describe('preview page size persistence', () => {
  it('defaults to 50 and only persists known sizes', () => {
    expect(readPreviewPageSize()).toBe(50);
    expect(persistPreviewPageSize(30)).toBe(false);
    expect(readPreviewPageSize()).toBe(50);
    expect(persistPreviewPageSize(100)).toBe(true);
    expect(readPreviewPageSize()).toBe(100);
  });
});
