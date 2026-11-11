/**
 * Horizontal wrap cluster with alignment options: the parent owns the space between
 * its children.
 *
 * USAGE:
 *   <Cluster justify="between">…</Cluster>
 *   <Cluster gap="stack" className="min-w-0">…</Cluster>
 *   <Cluster gap="stack" wrap={false}>…</Cluster>   // one line, e.g. a header view switcher
 *   <Cluster justify="between" align="start">…</Cluster>   // top-aligned title + actions
 *
 * Gap names are spacing roles, each mapped to its `--gap-*` token; `xs` (4) is for
 * component internals only.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import { cn } from '../lib/cn';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type ClusterGap = 'xs' | 'stack' | 'heading' | 'block';

export interface ClusterProps {
  /** Spacing role between children. Default 'heading' (--gap-heading, 12). */
  gap?: ClusterGap;
  justify?: 'start' | 'between' | 'end';
  /** Cross-axis alignment. Default 'center'. */
  align?: 'start' | 'center' | 'end' | 'baseline';
  /** Wrap onto new lines (default). `false` keeps one line for a scrolling host. */
  wrap?: boolean;
  className?: string;
  children: ReactNode;
}

const GAPS: Record<ClusterGap, string> = {
  xs: 'gap-1',
  stack: 'gap-[var(--gap-stack)]',
  heading: 'gap-[var(--gap-heading)]',
  block: 'gap-[var(--gap-block)]',
};
const JUSTIFY = { start: 'justify-start', between: 'justify-between', end: 'justify-end' };
const ALIGN = {
  start: 'items-start',
  center: 'items-center',
  end: 'items-end',
  baseline: 'items-baseline',
};

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Cluster({
  gap = 'heading',
  justify = 'start',
  align = 'center',
  wrap = true,
  className,
  children,
}: ClusterProps) {
  return (
    <div
      className={cn(
        'flex',
        wrap ? 'flex-wrap' : 'flex-nowrap',
        ALIGN[align],
        GAPS[gap],
        JUSTIFY[justify],
        className,
      )}
    >
      {children}
    </div>
  );
}
