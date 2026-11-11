/**
 * Portable table module: primitives, sort headers and composed tables. Callers pass
 * data, columns and presentation metadata; styling lives in the kit.
 *
 * USAGE:
 *   import { DataTable, MetricComparisonTable, Table, TableCell } from '@quant-factory/qf-ui/tables';
 *   import { sortRows, type SortState } from '@quant-factory/qf-ui/tables/core';
 */

// --------------------------------------------------------------------------- #
// Cascade layers (first, so kit CSS never precedes the layer order)
// --------------------------------------------------------------------------- #

import '../styles/layers.css';

// --------------------------------------------------------------------------- #
// Primitives
// --------------------------------------------------------------------------- #

export * from './primitives/SortHeader';
export * from './primitives/Table';

// --------------------------------------------------------------------------- #
// Cell kinds
// --------------------------------------------------------------------------- #

export type { CellKind, DataTableColumn, TableRecord } from './cells/cells';

// --------------------------------------------------------------------------- #
// Composed tables
// --------------------------------------------------------------------------- #

export * from './composed/DataTable';
export * from './composed/MetricComparisonTable';
