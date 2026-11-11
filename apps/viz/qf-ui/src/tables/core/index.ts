/**
 * Headless table helpers: sort state and ordering, column number formatting.
 * No React DOM and no CSS, so services, workers and tests can import it freely.
 *
 * USAGE:
 *   import { columnFormat, nextSort, sortRows } from '@quant-factory/qf-ui/tables/core';
 *   const ordered = sortRows(rows, nextSort(sort, 'close'));
 */

// --------------------------------------------------------------------------- #
// Sorting
// --------------------------------------------------------------------------- #

export * from './sort';

// --------------------------------------------------------------------------- #
// Column formatting
// --------------------------------------------------------------------------- #

export * from './format';
