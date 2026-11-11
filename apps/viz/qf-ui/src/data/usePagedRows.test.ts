/**
 * Tests for the server-paged row-range footer label.
 *
 * USAGE: pnpm --dir apps/viz/qf-ui test -- usePagedRows
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';
import { formatRowRangeLabel } from './usePagedRows';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('formatRowRangeLabel', () => {
  it('renders the absolute row window and page position', () => {
    expect(
      formatRowRangeLabel({
        page: 1_785_320,
        pageSize: 50,
        returnedRows: 50,
        totalRows: 89_266_000,
        totalPages: 1_785_320,
      }),
    ).toBe('Rows 89,265,951–89,266,000 of 89,266,000 · page 1,785,320 of 1,785,320');
  });

  it('degrades safely on an empty page', () => {
    expect(
      formatRowRangeLabel({ page: 1, pageSize: 50, returnedRows: 0, totalRows: 0, totalPages: 1 }),
    ).toBe('Rows 0 of 0 · page 1 of 1');
  });
});
