/**
 * Pure column projection helpers for wide parquet previews.
 *
 * USAGE:
 *   const page = selectDatasetColumns(schemaNames, search, pageNumber);
 */

// --------------------------------------------------------------------------- #
// Constants and types
// --------------------------------------------------------------------------- #

export const DATASET_COLUMN_PAGE_SIZE = 50;
const IDENTITY_COLUMN_PRIORITY = [
  'timestamp',
  'date',
  'datetime',
  'symbol',
  'asset',
  'ticker',
  'id',
] as const;

export interface DatasetColumnPage {
  pinned: string[];
  browsable: string[];
  selected: string[];
  page: number;
  totalPages: number;
  totalBrowsable: number;
  start: number;
  end: number;
}

// --------------------------------------------------------------------------- #
// Selection
// --------------------------------------------------------------------------- #

export function selectIdentityColumns(columns: string[]): string[] {
  const byLowercase = new Map(columns.map((column) => [column.toLowerCase(), column]));
  return IDENTITY_COLUMN_PRIORITY.flatMap((candidate) => {
    const match = byLowercase.get(candidate);
    return match ? [match] : [];
  }).slice(0, 2);
}

export function selectDatasetColumns(
  columns: string[],
  search: string,
  requestedPage: number,
): DatasetColumnPage {
  const pinned = selectIdentityColumns(columns);
  const pinnedSet = new Set(pinned);
  const normalizedSearch = search.trim().toLowerCase();
  const browsable = columns.filter(
    (column) =>
      !pinnedSet.has(column) &&
      (!normalizedSearch || column.toLowerCase().includes(normalizedSearch)),
  );
  const totalPages = Math.max(1, Math.ceil(browsable.length / DATASET_COLUMN_PAGE_SIZE));
  const page = Math.min(Math.max(requestedPage, 1), totalPages);
  const startIndex = (page - 1) * DATASET_COLUMN_PAGE_SIZE;
  const pageColumns = browsable.slice(startIndex, startIndex + DATASET_COLUMN_PAGE_SIZE);
  return {
    pinned,
    browsable,
    selected: [...pinned, ...pageColumns],
    page,
    totalPages,
    totalBrowsable: browsable.length,
    start: browsable.length ? startIndex + 1 : 0,
    end: Math.min(startIndex + DATASET_COLUMN_PAGE_SIZE, browsable.length),
  };
}

/**
 * Whether a viewer must offer the column search and pager.
 *
 * Compact chrome hides them to keep a narrow panel quiet, which is right for a
 * dataset whose columns all fit on one page and wrong for a wide feature panel:
 * without them every column past the first page is unreachable.
 */
export function showsColumnControls(
  compactChrome: boolean,
  totalPages: number,
  search: string,
): boolean {
  return !compactChrome || totalPages > 1 || Boolean(search);
}
