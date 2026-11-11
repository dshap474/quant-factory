/**
 * Page navigation for paged tables: range label, optional page-size select and
 * go-to-page input, Previous/Next controls.
 *
 * USAGE:
 *   <Pagination page={page} pageCount={pages} onPageChange={setPage} label={formatRowRangeLabel(…)} />
 *   <Pagination
 *     page={page} pageCount={pages} onPageChange={setPage}
 *     pageSize={size} pageSizeOptions={[25, 50, 100]} onPageSizeChange={setSize}
 *     jump disabled={isFetching}
 *   />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { type ReactNode, useId, useState } from 'react';

import { cn } from '../lib/cn';
import { Button } from '../primitives/Button';
import { Field } from '../primitives/Field';
import { Input } from '../primitives/Input';
import { SelectControl } from '../primitives/Select';

import './Pagination.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface PaginationProps {
  /** 1-based current page. */
  page: number;
  /** Total pages; 0 or 1 disables both direction controls. */
  pageCount: number;
  onPageChange: (page: number) => void;
  /** Range text at the start, e.g. the output of formatRowRangeLabel. */
  label?: ReactNode;
  /** Page-size select; rendered when all three page-size props are given. */
  pageSize?: number;
  pageSizeOptions?: readonly number[];
  onPageSizeChange?: (size: number) => void;
  /** Renders a go-to-page input (Enter jumps). */
  jump?: boolean;
  /** Disables every control, e.g. while the next page is fetching. */
  disabled?: boolean;
  /** Render as the bottom band of a bounded table shell: top hairline, inset by `--ui-band-inset`. */
  band?: boolean;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Pagination({
  page,
  pageCount,
  onPageChange,
  label,
  pageSize,
  pageSizeOptions,
  onPageSizeChange,
  jump = false,
  disabled = false,
  band = false,
  className,
}: PaginationProps) {
  const id = useId();
  const [draft, setDraft] = useState('');
  const hasPrevious = page > 1;
  const hasNext = page < pageCount;

  function jumpToDraft() {
    const target = Number(draft);
    setDraft('');
    if (!Number.isInteger(target) || target < 1 || target > pageCount || target === page) return;
    onPageChange(target);
  }

  return (
    <nav
      aria-label="Pagination"
      className={cn('ui-pagination', band && 'ui-pagination-band', className)}
    >
      {label !== undefined ? <span className="ui-pagination-label">{label}</span> : null}
      <div className="ui-pagination-controls">
        {jump ? (
          <Field label="Go to page" htmlFor={`${id}-jump`} layout="inline">
            <Input
              id={`${id}-jump`}
              type="number"
              min={1}
              max={Math.max(1, pageCount)}
              className="ui-pagination-jump"
              value={draft}
              placeholder={String(page)}
              disabled={disabled}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key !== 'Enter') return;
                event.preventDefault();
                jumpToDraft();
              }}
            />
          </Field>
        ) : null}
        {pageSize !== undefined &&
        pageSizeOptions !== undefined &&
        onPageSizeChange !== undefined ? (
          <Field label="Rows" htmlFor={`${id}-size`} layout="inline">
            <SelectControl
              id={`${id}-size`}
              value={String(pageSize)}
              disabled={disabled}
              onValueChange={(value) => onPageSizeChange(Number(value))}
              options={pageSizeOptions.map((size) => ({
                value: String(size),
                label: String(size),
              }))}
            />
          </Field>
        ) : null}
        <Button
          type="button"
          variant="control"
          disabled={disabled || !hasPrevious}
          onClick={() => onPageChange(page - 1)}
        >
          Previous
        </Button>
        <Button
          type="button"
          variant="control"
          disabled={disabled || !hasNext}
          onClick={() => onPageChange(page + 1)}
        >
          Next
        </Button>
      </div>
    </nav>
  );
}
