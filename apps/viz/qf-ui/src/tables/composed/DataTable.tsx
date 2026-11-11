/**
 * Simple tabular data renderer, with an opt-in terminal data-grid mode.
 *
 * USAGE:
 *   <DataTable data={rows} columns={['a','b']} linkColumn="name" maxRows={50} />
 *   <DataTable data={rows} columns={cols} dense rowOffset={200} columnTypes={dtypes} />
 *   <DataTable data={rows} columns={cols} dense loading={isFetchingPage} />
 *   <DataTable data={rows} columns={cols} sortable defaultSort={{ column: 'close', direction: 'desc' }} />
 *   <DataTable data={rows} columns={cols} sortable sort={sort} onSortChange={setSort} />  // host orders rows
 *   <DataTable data={rows} columns={cols} dense flush fill />  // host supplies chrome and bounds height
 *   <DataTable data={rows} columns={cols} maxRows={50_000} virtualize fill />  // windowed rows
 *   <DataTable data={rows} columns={cols} maxRows={50_000} virtualize={{ rowHeight: 28, overscan: 12 }} />
 *   <DataTable data={rows} columns={cols} dense pageSize={10} />  // client-side pages + Pagination
 *   <DataTable data={rows} columns={[{ key: 'mint', kind: 'identifier' }, { key: 'pnl', kind: 'money' }]} />
 *
 * `columns` takes bare keys (text columns headed by the key) or `DataTableColumn`
 * objects with a cell kind (see `tables/cells`): numeric kinds right-align, heat tints,
 * identifiers and statuses render through the kit components. Plain columns whose page
 * values are all numbers right-align too, head and cells, in either density.
 *
 * `pageSize` pages the (sorted) rows on the client and renders the qf-ui Pagination with a
 * range label below the table once there is more than one page; it replaces `maxRows`.
 *
 * Virtualization keeps a fixed-height window of rows in the DOM (spacer rows stand in for
 * the rest), so pair it with a bounded scroll region (`fill` in a sized host, or the default
 * 65vh cap) and raise `maxRows`, which still caps how many rows are considered. Below
 * VIRTUALIZE_MIN_ROWS rows it renders everything, since a window buys nothing there.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useVirtualizer } from '@tanstack/react-virtual';
import { useRef, useState } from 'react';
import { Pagination } from '../../data/Pagination';
import { formatPageRangeLabel, usePagination } from '../../data/usePagedRows';
import { ScrollArea } from '../../layout/ScrollArea';
import { cn } from '../../lib/cn';
import { Link } from '../../primitives/Link';
import { EmptyState } from '../../state/EmptyState';
import {
  cellContent,
  cellHeat,
  cellValue,
  type DataTableColumn,
  isDeclaredCell,
  isNumericKind,
  resolveColumns,
  type TableRecord,
} from '../cells/cells';
import { type ColumnFormat, columnFormat, formatGrouped, isNumericDtype } from '../core/format';
import { type SortState, sortRows } from '../core/sort';
import { SortHeader } from '../primitives/SortHeader';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../primitives/Table';

import './DataTable.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface DataTableVirtualize {
  /** Fixed row height in px. Rows are pinned to it so the scroll extent is exact. */
  rowHeight: number;
  /** Rows rendered beyond the visible window on each side. Defaults to 8. */
  overscan?: number;
}

export interface DataTableProps<Row extends object = TableRecord> {
  data: readonly Row[];
  /** Bare keys or declarative columns with a cell kind; defaults to the first row's keys. */
  columns?: readonly (string | DataTableColumn<Row>)[];
  maxRows?: number;
  /** Column whose cells link to row.link when present. */
  linkColumn?: string;
  /** Stable row identity. Immutable preview pages intentionally fall back to page-local index. */
  rowKey?: (row: Row, index: number) => string | number;
  /** Terminal data-grid presentation: content-width columns, row gutter, ditto and null glyphs. */
  dense?: boolean;
  /** Absolute index of the first rendered row. Its presence renders the dense row-number gutter. */
  rowOffset?: number;
  /** Column dtypes rendered as a dim second header line in dense mode. */
  columnTypes?: Record<string, string>;
  /** Renders skeleton rows in the live grid instead of data rows or stale rows. */
  loading?: boolean;
  /** Skeleton row count. Defaults to the currently rendered row count. */
  skeletonRows?: number;
  /** Empty-result copy rendered inside the table region at stable height. */
  emptyTitle?: string;
  emptyHint?: string;
  /** Sortable columns: `true` for every column or an explicit list. Headers get aria-sort and a sort button. */
  sortable?: boolean | readonly string[];
  /** Initial sort when DataTable orders rows itself (no onSortChange). */
  defaultSort?: SortState | null;
  /** Controlled sort. With onSortChange the host orders `data`; DataTable only renders the state. */
  sort?: SortState | null;
  onSortChange?: (next: SortState) => void;
  /**
   * Window the rows with @tanstack/react-virtual. `true` uses the default row height (22px
   * dense, 33px otherwise); an object sets it. Ignored while loading or under
   * VIRTUALIZE_MIN_ROWS rows.
   */
  virtualize?: boolean | DataTableVirtualize;
  /** The host supplies the border: no frame border or radius. */
  flush?: boolean;
  /** Fill a bounded flex-column host; the scroll region takes the host height instead of capping at 65vh. */
  fill?: boolean;
  /**
   * Client-side paging: show this many rows per page and render the qf-ui Pagination below
   * the table when there is more than one page. Replaces `maxRows`; skeletons default to it.
   */
  pageSize?: number;
  /** Merged onto the outer frame. */
  className?: string;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const TEMPORAL_COLUMNS = new Set(['timestamp', 'datetime', 'date', 'time']);
const NULL_GLYPH = '∅';
/** Row count at or below which `virtualize` renders every row. */
export const VIRTUALIZE_MIN_ROWS = 50;
const DEFAULT_OVERSCAN = 8;
/** Rendered row heights (--table-row-height-compact and --table-row-height), so the
    virtualizer's estimate matches the rows. */
const DENSE_ROW_HEIGHT = 28;
const DEFAULT_ROW_HEIGHT = 32;
/** First-render window for measure-less environments (SSR, jsdom) before the observer reports. */
const INITIAL_WINDOW_ROWS = 24;
const HEAD_CLASS = 'data-table-head';
/** Identifier-like columns keep Plex Mono; every other body cell is sans with tabular figures. */
const MONO_COLUMN = /(^|_)(id|hash|sha|uuid|path|address)$/i;

function isMonoColumn(column: string): boolean {
  return MONO_COLUMN.test(column);
}

/** Identifiers and years read as labels, so they skip thousands separators. */
function isUngrouped(column: string): boolean {
  return isMonoColumn(column) || /(^|_)year$/i.test(column);
}

function isTemporal(column: string): boolean {
  return TEMPORAL_COLUMNS.has(column.toLowerCase());
}

function formatEpoch(value: number): string | null {
  const magnitude = Math.abs(value);
  let milliseconds: number;
  if (magnitude >= 100_000_000_000_000_000) milliseconds = value / 1_000_000;
  else if (magnitude >= 100_000_000_000_000) milliseconds = value / 1_000;
  else if (magnitude >= 100_000_000_000) milliseconds = value;
  else if (magnitude >= 100_000_000) milliseconds = value * 1_000;
  else return null;

  const date = new Date(milliseconds);
  return Number.isNaN(date.getTime()) ? null : date.toISOString().replace('.000Z', 'Z');
}

function resolveVirtualize(
  virtualize: DataTableProps['virtualize'],
  dense: boolean,
): { rowHeight: number; overscan: number } | null {
  if (!virtualize) return null;
  const defaultHeight = dense ? DENSE_ROW_HEIGHT : DEFAULT_ROW_HEIGHT;
  if (virtualize === true) return { rowHeight: defaultHeight, overscan: DEFAULT_OVERSCAN };
  return { rowHeight: virtualize.rowHeight, overscan: virtualize.overscan ?? DEFAULT_OVERSCAN };
}

/** Sort through a column's `value` accessor when it has one, else by the raw field. */
function orderRows(
  data: readonly TableRecord[],
  sort: SortState,
  columns: readonly DataTableColumn[],
): readonly TableRecord[] {
  const accessor = columns.find((column) => column.key === sort.column)?.value;
  if (!accessor) return sortRows([...data], sort);
  const keyed = data.map((row) => ({ sortValue: accessor(row), row }));
  return sortRows(keyed, { ...sort, column: 'sortValue' }).map((entry) => entry.row);
}

function formatCell(column: string, value: unknown, format?: ColumnFormat): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === 'number') {
    if (isTemporal(column)) {
      const temporalValue = formatEpoch(value);
      if (temporalValue) return temporalValue;
    }
    if (format?.numeric) {
      return isUngrouped(column) ? value.toFixed(format.scale) : formatGrouped(value, format.scale);
    }
    if (Number.isInteger(value)) return value.toString();
    return value.toFixed(4);
  }
  return String(value);
}

// --------------------------------------------------------------------------- #
// Virtual window
// --------------------------------------------------------------------------- #

/** Stands in for the rows outside the window so the scroll extent stays exact. */
function SpacerRow({ height, span }: { height: number; span: number }) {
  return (
    <TableRow aria-hidden="true" className="data-table-spacer hover:bg-transparent">
      <TableCell colSpan={span} style={{ height, padding: 0, border: 0 }} />
    </TableRow>
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function DataTable<Row extends object = TableRecord>({
  data: rows,
  columns: columnsProp,
  maxRows = 50,
  linkColumn,
  rowKey: rowKeyProp,
  dense = false,
  rowOffset,
  columnTypes,
  loading = false,
  skeletonRows,
  emptyTitle = 'No rows',
  emptyHint,
  sortable = false,
  defaultSort = null,
  sort,
  onSortChange,
  virtualize,
  flush = false,
  fill = false,
  pageSize,
  className,
}: DataTableProps<Row>) {
  // Rendering reads fields by key, so the typed rows and columns are viewed as records.
  const data = rows as unknown as readonly TableRecord[];
  const columns = columnsProp as readonly (string | DataTableColumn)[] | undefined;
  const rowKey = rowKeyProp as ((row: TableRecord, index: number) => string | number) | undefined;
  const [internalSort, setInternalSort] = useState<SortState | null>(defaultSort);
  const controlled = onSortChange !== undefined;
  const activeSort = controlled ? (sort ?? null) : internalSort;
  const columnDefs = resolveColumns(columns ?? (data[0] ? Object.keys(data[0]) : []));
  const displayColumns = columnDefs.map((column) => column.key);
  const sortableColumns = new Set<string>(
    sortable === true ? displayColumns : sortable === false ? [] : sortable,
  );
  const orderedData =
    controlled || activeSort === null ? data : orderRows(data, activeSort, columnDefs);
  const paging = usePagination({ count: orderedData.length, pageSize: pageSize ?? 1 });
  const pageData =
    pageSize === undefined
      ? orderedData.slice(0, maxRows)
      : orderedData.slice(paging.start, paging.end);
  const displayData = loading ? [] : pageData;
  const absoluteOffset = rowOffset ?? (pageSize === undefined ? 0 : paging.start);
  const skeletonCount = Math.max(
    1,
    skeletonRows ?? pageSize ?? (data.length ? Math.min(data.length, maxRows) : 8),
  );
  const isEmpty = !loading && displayData.length === 0;
  const windowing = resolveVirtualize(virtualize, dense);
  const virtual = windowing !== null && !loading && displayData.length > VIRTUALIZE_MIN_ROWS;
  const rowHeight = windowing?.rowHeight ?? DEFAULT_ROW_HEIGHT;
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const virtualizer = useVirtualizer({
    count: virtual ? displayData.length : 0,
    estimateSize: () => rowHeight,
    getScrollElement: () => scrollRef.current,
    overscan: windowing?.overscan ?? DEFAULT_OVERSCAN,
    initialRect: { width: 0, height: rowHeight * INITIAL_WINDOW_ROWS },
    enabled: virtual,
  });
  const virtualItems = virtual ? virtualizer.getVirtualItems() : [];
  const bodyIndices = virtual
    ? virtualItems.map((item) => item.index)
    : displayData.map((_, rowIndex) => rowIndex);
  const spacerTop = virtualItems[0]?.start ?? 0;
  const spacerBottom = virtual
    ? Math.max(0, virtualizer.getTotalSize() - (virtualItems.at(-1)?.end ?? 0))
    : 0;
  const formats = new Map<string, ColumnFormat>();
  if (dense) {
    for (const column of columnDefs) {
      if (isDeclaredCell(column)) continue;
      formats.set(
        column.key,
        columnFormat(
          displayData.map((row) => cellValue(column, row)),
          isTemporal(column.key),
        ),
      );
    }
  }
  // Numeric columns right-align head and cells in every density: declared numeric kinds,
  // plain columns with a numeric dtype (so an all-null page keeps its side), and plain
  // columns whose non-null page values are all finite numbers.
  const numericColumns = new Set<string>();
  for (const column of columnDefs) {
    const numeric = isDeclaredCell(column)
      ? isNumericKind(column.kind)
      : isNumericDtype(columnTypes?.[column.key]) ||
        (
          formats.get(column.key) ??
          columnFormat(
            displayData.map((row) => cellValue(column, row)),
            isTemporal(column.key),
          )
        ).numeric;
    if (numeric) numericColumns.add(column.key);
  }
  const dittoColumn = dense
    ? columnDefs.find((column) => !isDeclaredCell(column) && isTemporal(column.key))?.key
    : undefined;
  const showGutter = dense && rowOffset !== undefined;
  const spanCount = displayColumns.length + (showGutter ? 1 : 0);
  const frameClass = cn(
    'data-table-frame',
    dense && 'data-table-dense',
    fill && 'is-fill',
    !flush && 'is-framed border border-border',
    !flush && 'rounded-surface',
    className,
  );

  function handleSortChange(next: SortState) {
    if (!controlled) setInternalSort(next);
    onSortChange?.(next);
  }

  function isNumericColumn(column: DataTableColumn): boolean {
    if (column.kind !== undefined) return isNumericKind(column.kind);
    return data.some((row) => typeof cellValue(column, row) === 'number');
  }

  function pagination() {
    if (pageSize === undefined || loading || orderedData.length <= pageSize) return null;
    return (
      <Pagination
        band
        page={paging.page}
        pageCount={paging.pageCount}
        onPageChange={paging.setPage}
        label={formatPageRangeLabel({ ...paging, total: orderedData.length })}
      />
    );
  }

  // Match the chart frame's 1px, subtle edge in both populated and empty states.
  const frameStyle = flush ? undefined : { borderColor: 'var(--color-border-subtle)' };

  if (displayColumns.length === 0) {
    return (
      <div className={cn(frameClass, 'data-table-stateframe')} style={frameStyle}>
        {loading ? (
          <div className="data-table-statebox" role="status" aria-label="Loading rows" />
        ) : (
          <EmptyState title={emptyTitle} hint={emptyHint} />
        )}
        {pagination()}
      </div>
    );
  }

  return (
    <div className={frameClass} style={frameStyle}>
      <ScrollArea
        axis="both"
        fill={fill}
        label="Scrollable data table"
        aria-busy={loading}
        className="data-table-scroll"
        ref={scrollRef}
      >
        <Table
          className={`border-collapse ${dense ? 'data-table-grid' : 'min-w-full'}`}
          aria-rowcount={virtual ? displayData.length + 1 : undefined}
        >
          <TableHeader sticky>
            <TableRow className="bg-card hover:bg-card">
              {showGutter ? (
                <TableHead className="data-table-gutter data-table-gutter-head sticky top-0 z-20">
                  <span className="sr-only">Row</span>
                </TableHead>
              ) : null}
              {columnDefs.map((column) => {
                const col = column.key;
                const numericHead = numericColumns.has(col);
                const label = (
                  <>
                    <span className="data-table-head-name">{column.header ?? col}</span>
                    {dense && columnTypes?.[col] ? (
                      <span className="data-table-head-type">{columnTypes[col]}</span>
                    ) : null}
                  </>
                );
                return sortableColumns.has(col) ? (
                  <SortHeader
                    key={col}
                    column={col}
                    sort={activeSort}
                    onSortChange={handleSortChange}
                    initialDirection={isNumericColumn(column) ? 'desc' : 'asc'}
                    numeric={numericHead}
                    className={HEAD_CLASS}
                  >
                    {label}
                  </SortHeader>
                ) : (
                  <TableHead key={col} numeric={numericHead} className={HEAD_CLASS}>
                    {label}
                  </TableHead>
                );
              })}
            </TableRow>
          </TableHeader>
          <TableBody
            data-indexed-rows=""
            className={loading ? 'motion-safe:animate-pulse' : undefined}
          >
            {loading
              ? Array.from({ length: skeletonCount }, (_, rowIndex) => (
                  <TableRow
                    key={`skeleton-${rowIndex}`}
                    className="hover:bg-transparent"
                    data-zebra={(absoluteOffset + rowIndex) % 2 === 1 ? '' : undefined}
                  >
                    {showGutter ? (
                      <TableCell className="data-table-gutter sticky left-0 z-10">
                        {((rowOffset ?? 0) + rowIndex + 1).toLocaleString()}
                      </TableCell>
                    ) : null}
                    {displayColumns.map((col) => (
                      <TableCell key={col} className="whitespace-nowrap data-table-cell">
                        <span className="data-table-skeleton-bar" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              : null}
            {isEmpty ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={spanCount} className="data-table-emptycell p-0">
                  <EmptyState title={emptyTitle} hint={emptyHint} />
                </TableCell>
              </TableRow>
            ) : null}
            {virtual && spacerTop > 0 ? <SpacerRow height={spacerTop} span={spanCount} /> : null}
            {bodyIndices.map((rowIndex) => {
              const row = displayData[rowIndex];
              if (row === undefined) return null;
              const previousRow = rowIndex > 0 ? displayData[rowIndex - 1] : undefined;
              return (
                <TableRow
                  key={rowKey ? rowKey(row, rowIndex) : rowIndex}
                  data-zebra={(absoluteOffset + rowIndex) % 2 === 1 ? '' : undefined}
                  aria-rowindex={virtual ? rowIndex + 2 : undefined}
                  style={virtual ? { height: rowHeight } : undefined}
                >
                  {showGutter ? (
                    <TableCell className="data-table-gutter sticky left-0 z-10">
                      {((rowOffset ?? 0) + rowIndex + 1).toLocaleString()}
                    </TableCell>
                  ) : null}
                  {columnDefs.map((column) => {
                    const col = column.key;
                    if (isDeclaredCell(column)) {
                      const value = cellValue(column, row);
                      const heat = cellHeat(column, value);
                      return (
                        <TableCell
                          key={col}
                          numeric={numericColumns.has(col)}
                          {...(heat ? { heat } : {})}
                          title={column.title?.(value, row)}
                          className="whitespace-nowrap tabular-nums data-table-cell text-foreground"
                        >
                          {cellContent(column, value, row)}
                        </TableCell>
                      );
                    }
                    const format = formats.get(col);
                    const content = formatCell(col, cellValue(column, row), format);
                    const href =
                      col === linkColumn && typeof row.link === 'string' ? row.link : null;
                    const ditto =
                      dense &&
                      col === dittoColumn &&
                      previousRow !== undefined &&
                      content !== null &&
                      content === formatCell(col, cellValue(column, previousRow), format);
                    const tone =
                      dense && (content === null || ditto)
                        ? 'text-muted-foreground'
                        : 'text-foreground';
                    return (
                      <TableCell
                        key={col}
                        numeric={numericColumns.has(col)}
                        title={column.title?.(cellValue(column, row), row)}
                        className={cn(
                          'whitespace-nowrap tabular-nums data-table-cell',
                          isMonoColumn(col) && 'font-mono',
                          column.truncate === 'end' && 'data-table-truncate',
                          tone,
                        )}
                      >
                        {href ? (
                          <Link to={href} variant="inline">
                            {content ?? (dense ? NULL_GLYPH : '-')}
                          </Link>
                        ) : (
                          (content ?? (dense ? NULL_GLYPH : '-'))
                        )}
                      </TableCell>
                    );
                  })}
                </TableRow>
              );
            })}
            {virtual && spacerBottom > 0 ? (
              <SpacerRow height={spacerBottom} span={spanCount} />
            ) : null}
          </TableBody>
        </Table>
      </ScrollArea>
      {pageSize === undefined && !loading && data.length > maxRows ? (
        <div className="border-t border-border-subtle px-3 py-2 text-caption text-muted-foreground">
          Showing {maxRows} of {data.length} rows
        </div>
      ) : null}
      {pagination()}
    </div>
  );
}
