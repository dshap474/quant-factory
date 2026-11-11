/**
 * The one between-chart grid: gapped or hairline seams, fixed or auto-fit columns,
 * optionally filling a bounded host. Cells own the "chart shell fills the cell" rule.
 *
 * USAGE:
 *   <ChartGrid><ChartGridCell>…</ChartGridCell></ChartGrid>
 *   <ChartGrid variant="hairline" columns={2} fill>…</ChartGrid>
 *   <ChartGrid minColumnWidth="20rem">…</ChartGrid>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { CSSProperties, HTMLAttributes, ReactNode } from 'react';

import { cn } from '../lib/cn';

import './ChartGrid.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ChartGridProps {
  /** 'gapped' (default): --space-4 gutters. 'hairline': 1px seams over the border colour. */
  variant?: 'gapped' | 'hairline';
  /** Fixed column count. Omit for auto-fit columns that drop to one column when narrow. */
  columns?: number;
  /** Auto-fit minimum column width (any CSS length). Default '32.47rem'. Ignored with columns. */
  minColumnWidth?: string;
  /** Rows share the bounded host height. Default: rows size to content / chart aspect ratio. */
  fill?: boolean;
  className?: string;
  children: ReactNode;
}

export interface ChartGridCellProps extends HTMLAttributes<HTMLDivElement> {
  /** Outline the cell as the assignment target. */
  target?: boolean;
  children: ReactNode;
}

type ChartGridStyle = CSSProperties &
  Partial<Record<'--ui-chart-grid-columns' | '--ui-chart-grid-min', string>>;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function gridStyle(columns?: number, minColumnWidth?: string): ChartGridStyle | undefined {
  if (columns !== undefined) return { '--ui-chart-grid-columns': String(columns) };
  if (minColumnWidth !== undefined) return { '--ui-chart-grid-min': minColumnWidth };
  return undefined;
}

// --------------------------------------------------------------------------- #
// Components
// --------------------------------------------------------------------------- #

export function ChartGridCell({ target, className, children, ...rest }: ChartGridCellProps) {
  return (
    <div className={cn('ui-chart-grid-cell', target && 'is-target', className)} {...rest}>
      {children}
    </div>
  );
}

export function ChartGrid({
  variant = 'gapped',
  columns,
  minColumnWidth,
  fill,
  className,
  children,
}: ChartGridProps) {
  return (
    <div
      className={cn(
        'ui-chart-grid',
        variant === 'hairline' ? 'is-hairline' : 'is-gapped',
        columns !== undefined && 'is-fixed',
        fill && 'is-fill',
        className,
      )}
      style={gridStyle(columns, minColumnWidth)}
    >
      {children}
    </div>
  );
}
