/**
 * Declarative cell kinds for DataTable: a column names its key and kind, the kit formats,
 * aligns, tints and renders the value. Pages pass data, kinds and options, never classes.
 *
 * USAGE:
 *   const columns: DataTableColumn[] = [
 *     { key: 'mint', header: 'Token', kind: 'identifier', truncate: 'middle' },
 *     { key: 'trades', header: 'Trades', kind: 'count' },
 *     { key: 'ic', header: '5d', kind: 'heat', heat: { maxAbs: 0.08 }, digits: 3 },
 *     { key: 'state', header: 'Status', kind: 'status' },
 *     { key: 'launched', header: 'Launch (UTC)', format: (value) => formatUtc(value) },
 *     { key: 'note', render: (value, row) => <Link to={row.href}>{String(value)}</Link> },
 *   ];
 *   <DataTable data={rows} columns={columns} />
 *
 * Numeric kinds (`number`, `percent`, `money`, `count`, `heat`) right-align their header
 * and cells and format through the shared `lib/number-format` helpers, so a missing value
 * reads as the kit's em dash. `format` replaces the text of any kind; `render` replaces the
 * whole cell content. `value` reads a derived value (also used for sorting).
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import type { DivergingCellColorOptions } from '../../lib/heat';
import {
  EMPTY,
  formatCount,
  formatMoney,
  formatNumber,
  formatPercent,
} from '../../lib/number-format';
import { Identifier, type IdentifierTruncate } from '../../primitives/Identifier';
import { StatusBadge } from '../../state/Status';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type TableRecord = Record<string, unknown>;

export type CellKind =
  | 'text'
  | 'number'
  | 'percent'
  | 'money'
  | 'count'
  | 'heat'
  | 'identifier'
  | 'status';

/** A column over rows of type `Row` (any object; defaults to a plain record). */
export interface DataTableColumn<Row extends object = TableRecord> {
  /** Row field, sort key and React key. */
  key: string;
  /** Header label; defaults to `key`. */
  header?: string;
  /** Formatting, alignment and rendering recipe. Defaults to `text`. */
  kind?: CellKind;
  /** Derived value for display and sorting; defaults to `row[key]`. */
  value?(row: Row): unknown;
  /** Display text for any kind (heat still tints from the value). */
  format?(value: unknown, row: Row): string;
  /** Full custom cell content; wins over `kind` and `format`. */
  render?(value: unknown, row: Row): ReactNode;
  /** Native tooltip for the cell. */
  title?(value: unknown, row: Row): string | undefined;
  /** Decimal places for `number` (3), `percent` (1), `money` (2) and `heat` (3). */
  digits?: number;
  /** Heat scale for `heat` cells (`maxAbs`, `magnitude`). */
  heat?: DivergingCellColorOptions;
  /** `identifier`: `end` (default) or `middle`. `text`: `end` caps the cell and ellipsizes. */
  truncate?: IdentifierTruncate;
}

// --------------------------------------------------------------------------- #
// Column helpers
// --------------------------------------------------------------------------- #

const NUMERIC_KINDS = new Set<CellKind>(['number', 'percent', 'money', 'count', 'heat']);

/** Columns given as bare keys become text columns with that key as their header. */
export function resolveColumns(columns: readonly (string | DataTableColumn)[]): DataTableColumn[] {
  return columns.map((column) => (typeof column === 'string' ? { key: column } : column));
}

export function isNumericKind(kind: CellKind | undefined): boolean {
  return kind !== undefined && NUMERIC_KINDS.has(kind);
}

export function cellValue(column: DataTableColumn, row: TableRecord): unknown {
  return column.value ? column.value(row) : row[column.key];
}

/** True when the column renders through a kind, `format` or `render` rather than the
    plain-column path (epoch detection, dense column scale, null glyph). */
export function isDeclaredCell(column: DataTableColumn): boolean {
  return (
    (column.kind !== undefined && column.kind !== 'text') ||
    column.format !== undefined ||
    column.render !== undefined
  );
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' ? value : null;
}

/** Heat input for TableCell, or undefined for non-heat columns. */
export function cellHeat(column: DataTableColumn, value: unknown) {
  if (column.kind !== 'heat') return undefined;
  return { value: asNumber(value), ...column.heat };
}

/** Text a declared column shows for `value`; missing values read as the kit em dash. */
export function cellText(column: DataTableColumn, value: unknown, row: TableRecord): string {
  if (column.format) return column.format(value, row);
  switch (column.kind) {
    case 'number':
    case 'heat':
      return formatNumber(asNumber(value), column.digits ?? 3);
    case 'percent':
      return formatPercent(asNumber(value), column.digits ?? 1);
    case 'money':
      return formatMoney(asNumber(value), column.digits ?? 2);
    case 'count':
      return formatCount(asNumber(value));
    default:
      return value === null || value === undefined || value === '' ? EMPTY : String(value);
  }
}

/** Content for a declared column: custom render, identifier, status badge or text. */
export function cellContent(column: DataTableColumn, value: unknown, row: TableRecord): ReactNode {
  if (column.render) return column.render(value, row);
  if (column.format === undefined && value !== null && value !== undefined && value !== '') {
    if (column.kind === 'identifier') {
      return <Identifier value={String(value)} truncate={column.truncate ?? 'end'} />;
    }
    if (column.kind === 'status') {
      return <StatusBadge status={String(value)}>{String(value)}</StatusBadge>;
    }
  }
  return cellText(column, value, row);
}
