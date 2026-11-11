/**
 * Page state for tables and lists. `usePagination` tracks one page over `count`
 * items (client rows or a server total) and clamps the page when the count
 * shrinks; while the count is unknown it keeps the requested page. `usePagedRows`
 * applies it to an in-memory array and returns the current slice plus the props
 * for the qf-ui `Pagination`.
 *
 * USAGE:
 *   const paged = usePagedRows(rows, 10);
 *   <DataTable data={paged.rows} />
 *   {paged.paged ? <Pagination {...paged.pagination} /> : null}
 *
 *   const pages = usePagination({ count: query.data?.total, pageSize: 10 });
 *   useAttempts(id, pages.start);   // server offset
 *   <Pagination page={pages.page} pageCount={pages.pageCount} onPageChange={pages.setPage} />
 *   formatRowRangeLabel({ page: 1, pageSize: 50, returnedRows: 50, totalRows: 120, totalPages: 3 });
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useState } from 'react';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface RowRangeInput {
  page: number;
  pageSize: number;
  returnedRows: number;
  totalRows?: number;
  totalPages: number;
}

export interface PaginationOptions {
  /** Items across every page; `undefined` while a server total is still loading. */
  count: number | undefined;
  pageSize: number;
}

export interface PaginationState {
  /** 1-based current page, clamped to `pageCount` once the count is known. */
  page: number;
  /** At least 1. */
  pageCount: number;
  setPage: (page: number) => void;
  /** 0-based index (or server offset) of the first item on the page. */
  start: number;
  /** Exclusive end index of the page, capped at the count. */
  end: number;
}

/** The figures a range label reads. */
export interface PageRange {
  start: number;
  end: number;
  total: number;
  page: number;
  pageCount: number;
}

/** Props for the qf-ui `Pagination`, range label included. */
export interface PagedRowsPagination {
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
  label: string;
}

export interface PagedRows<Row> extends PaginationState {
  /** The rows on the current page. */
  rows: Row[];
  total: number;
  /** More rows than one page: render the pagination. */
  paged: boolean;
  pagination: PagedRowsPagination;
}

// --------------------------------------------------------------------------- #
// Hooks
// --------------------------------------------------------------------------- #

export function usePagination({ count, pageSize }: PaginationOptions): PaginationState {
  const [requested, setRequested] = useState(1);
  const size = Math.max(1, pageSize);
  const pageCount =
    count === undefined ? Math.max(1, requested) : Math.max(1, Math.ceil(count / size));
  const page = count === undefined ? requested : Math.min(requested, pageCount);
  const start = (page - 1) * size;
  const end = count === undefined ? start + size : Math.min(start + size, count);
  return { page, pageCount, setPage: setRequested, start, end };
}

/** Terminal footer status, e.g. `Rows 1–50 of 120 · page 1 of 3`. */
export function formatRowRangeLabel({
  page,
  pageSize,
  returnedRows,
  totalRows,
  totalPages,
}: RowRangeInput): string {
  const pageLabel = `page ${page.toLocaleString()} of ${Math.max(1, totalPages).toLocaleString()}`;
  if (returnedRows <= 0) {
    return `Rows 0 of ${(totalRows ?? 0).toLocaleString()} · ${pageLabel}`;
  }
  const start = (page - 1) * pageSize + 1;
  const end = start + returnedRows - 1;
  const total = totalRows ?? end;
  return `Rows ${start.toLocaleString()}–${end.toLocaleString()} of ${total.toLocaleString()} · ${pageLabel}`;
}

/** `start+1–end of total · page/pageCount`, the range label every paged table shows. */
export function formatPageRangeLabel({ start, end, total, page, pageCount }: PageRange): string {
  return `${start + 1}–${end} of ${total} · ${page}/${pageCount}`;
}

export function usePagedRows<Row>(rows: readonly Row[], pageSize: number): PagedRows<Row> {
  const state = usePagination({ count: rows.length, pageSize });
  const total = rows.length;
  return {
    ...state,
    rows: rows.slice(state.start, state.end),
    total,
    paged: total > pageSize,
    pagination: {
      page: state.page,
      pageCount: state.pageCount,
      onPageChange: state.setPage,
      label: formatPageRangeLabel({ ...state, total }),
    },
  };
}
