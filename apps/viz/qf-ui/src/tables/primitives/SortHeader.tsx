/**
 * Sortable column header: a `<th aria-sort>` wrapping one shared sort button.
 *
 * USAGE:
 *   <SortHeader column="close" sort={sort} onSortChange={setSort} initialDirection="desc">
 *     close
 *   </SortHeader>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import { cn } from '../../lib/cn';
import { ariaSort, nextSort, type SortDirection, type SortState } from '../core/sort';
import { TableHead, type TableHeadProps } from './Table';

import './SortHeader.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface SortHeaderProps extends TableHeadProps {
  column: string;
  sort: SortState | null;
  onSortChange: (next: SortState) => void;
  /** Direction a fresh click on this column starts with. Defaults to ascending. */
  initialDirection?: SortDirection;
  children: ReactNode;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

const GLYPHS: Record<SortDirection | 'none', string> = { asc: '↑', desc: '↓', none: '↕' };

export function SortHeader({
  column,
  sort,
  onSortChange,
  initialDirection = 'asc',
  children,
  ...props
}: SortHeaderProps) {
  const direction = sort && sort.column === column ? sort.direction : 'none';
  const active = direction !== 'none';
  return (
    <TableHead aria-sort={ariaSort(sort, column)} {...props}>
      <button
        type="button"
        className={cn('ui-sort-button', active && 'is-active')}
        onClick={() => onSortChange(nextSort(sort, column, initialDirection))}
      >
        <span>{children}</span>
        <span className="ui-sort-glyph" aria-hidden="true">
          {GLYPHS[direction]}
        </span>
      </button>
    </TableHead>
  );
}
