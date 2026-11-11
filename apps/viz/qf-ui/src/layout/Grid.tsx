/**
 * Responsive auto-fill grid with preset item widths; the grid owns its gutters.
 *
 * USAGE:
 *   <Grid>…</Grid>                                // 12rem items, block gutter
 *   <Grid minItemWidth="sm" gap="stack">…</Grid>  // 9rem items, tight gutter
 *   <Grid minItemWidth="lg">…</Grid>
 *
 * Gap names are spacing roles, each mapped to its `--gap-*` token.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import { cn } from '../lib/cn';

import './Grid.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type GridGap = 'stack' | 'heading' | 'block';

export interface GridProps {
  /** Minimum item width preset: sm 9rem, md 12rem, lg 14rem. */
  minItemWidth?: 'sm' | 'md' | 'lg';
  /** Spacing role between cells. Default 'block' (--gap-block, 16). */
  gap?: GridGap;
  className?: string;
  children: ReactNode;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Grid({ minItemWidth = 'md', gap = 'block', className, children }: GridProps) {
  return (
    <div className={cn('ui-grid', `is-min-${minItemWidth}`, `is-gap-${gap}`, className)}>
      {children}
    </div>
  );
}
