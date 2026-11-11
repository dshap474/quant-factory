/**
 * Column sort state and ordering helpers shared by DataTable and SortHeader.
 *
 * USAGE:
 *   const [sort, setSort] = useState<SortState | null>(null);
 *   <SortHeader column="close" sort={sort} onSortChange={setSort}>close</SortHeader>
 *   const ordered = sortRows(rows, sort);
 */

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type SortDirection = 'asc' | 'desc';

export interface SortState {
  column: string;
  direction: SortDirection;
}

export type AriaSort = 'ascending' | 'descending' | 'none';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const COLLATOR = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

function isMissing(value: unknown): boolean {
  return (
    value === null || value === undefined || (typeof value === 'number' && Number.isNaN(value))
  );
}

/** Clicking the active column flips it; clicking another column starts at `initial`. */
export function nextSort(
  current: SortState | null,
  column: string,
  initial: SortDirection = 'asc',
): SortState {
  if (!current || current.column !== column) return { column, direction: initial };
  return { column, direction: current.direction === 'asc' ? 'desc' : 'asc' };
}

export function ariaSort(sort: SortState | null, column: string): AriaSort {
  if (!sort || sort.column !== column) return 'none';
  return sort.direction === 'asc' ? 'ascending' : 'descending';
}

/** Ascending comparison: numbers numerically, everything else as text with numeric collation. */
export function compareValues(left: unknown, right: unknown): number {
  if (typeof left === 'number' && typeof right === 'number') return left - right;
  if (typeof left === 'boolean' && typeof right === 'boolean') return Number(left) - Number(right);
  return COLLATOR.compare(String(left), String(right));
}

/** Stable copy of `rows` ordered by `sort`; missing values (null/undefined/NaN) sort last either way. */
export function sortRows<T extends Record<string, unknown>>(
  rows: readonly T[],
  sort: SortState | null,
): T[] {
  if (!sort) return [...rows];
  const sign = sort.direction === 'asc' ? 1 : -1;
  return rows
    .map((row, index) => ({ row, index }))
    .sort((left, right) => {
      const a = left.row[sort.column];
      const b = right.row[sort.column];
      const aMissing = isMissing(a);
      const bMissing = isMissing(b);
      if (aMissing || bMissing) {
        if (aMissing && bMissing) return left.index - right.index;
        return aMissing ? 1 : -1;
      }
      const ordered = compareValues(a, b) * sign;
      return ordered !== 0 ? ordered : left.index - right.index;
    })
    .map((entry) => entry.row);
}
