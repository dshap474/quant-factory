/**
 * Explicit column tracks with a role-named gap: side-by-side panes or sections that
 * stack into one column below a breakpoint. Grid is the auto-fill sibling.
 *
 * USAGE:
 *   <Columns template="minmax(0,2fr) minmax(0,1fr)" from="xl" gap="section">…</Columns>
 *   <Columns template="20rem minmax(0,1fr)" from="lg">…</Columns>   // rail beside a pane
 *   <Columns template="repeat(2, minmax(0,1fr))" gap="heading">…</Columns>  // always two
 *   <Columns template="minmax(0,1fr) 20rem" from="xl" gap="block" rowGap="section">…</Columns>
 *
 * Gap names are spacing roles, each mapped to its `--gap-*` token. Breakpoints match the
 * host's md 48rem, lg 64rem and xl 80rem viewport widths.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { CSSProperties, HTMLAttributes, ReactNode } from 'react';

import { cn } from '../lib/cn';

import './Columns.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type ColumnsGap = 'stack' | 'heading' | 'block' | 'section';
export type ColumnsBreakpoint = 'md' | 'lg' | 'xl';

export interface ColumnsProps extends HTMLAttributes<HTMLDivElement> {
  /** CSS track list (grid-template-columns), e.g. 'minmax(0,2fr) minmax(0,1fr)'. */
  template: string;
  /** Viewport width from which the tracks apply; below it the columns stack. Omit to always apply. */
  from?: ColumnsBreakpoint;
  /** Spacing role between columns (and rows unless rowGap is set). Default 'block'. */
  gap?: ColumnsGap;
  /** Spacing role between rows when it differs from the column gap. */
  rowGap?: ColumnsGap;
  children: ReactNode;
}

type ColumnsStyle = CSSProperties & Record<'--ui-columns-template', string>;

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Columns({
  template,
  from,
  gap = 'block',
  rowGap,
  className,
  style,
  children,
  ...props
}: ColumnsProps) {
  const columnsStyle: ColumnsStyle = { ...style, '--ui-columns-template': template };
  return (
    <div
      className={cn(
        'ui-columns',
        from ? `is-from-${from}` : 'is-always',
        `is-gap-${gap}`,
        rowGap && `is-row-gap-${rowGap}`,
        className,
      )}
      style={columnsStyle}
      {...props}
    >
      {children}
    </div>
  );
}
