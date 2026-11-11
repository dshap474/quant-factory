/**
 * Padding box on the inset scale: the one owner of a region's edge inside a flush frame
 * (a clipped Surface, a ScrollArea, a band), so callers never pad with raw utilities.
 *
 * USAGE:
 *   <Inset padding="sm"><LoadingSkeleton /></Inset>          // 12 on every side
 *   <ScrollArea fill><Inset padding="md">…</Inset></ScrollArea>
 *   <Inset padding="sm" axis="inline">…</Inset>               // band row: inline edge only
 *   <ScrollArea fill><Inset padding="pane">…</Inset></ScrollArea>  // a pane's own scroller
 *   <Inset padding="tabs" axis="inline"><SegmentedControl variant="tabs" … /></Inset>
 *
 * sm is --inset-surface-compact (12), md is --inset-surface (16), lg is --inset-page (24).
 * pane is the scrolling-pane edge: --gap-block from the header or toolbar above, then
 * --inset-page on the sides and at the end (axis does not apply). tabs is the page inset
 * less a tab's own label padding, so a tab strip's labels sit on the page edge. none is for a host that
 * insets only in some modes, e.g. `padding={fill ? 'pane' : 'none'}`.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { HTMLAttributes, ReactNode } from 'react';

import { cn } from '../lib/cn';

import './Inset.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type InsetPadding = 'none' | 'sm' | 'md' | 'lg' | 'tabs' | 'pane';
export type InsetAxis = 'both' | 'inline' | 'block';

export interface InsetProps extends HTMLAttributes<HTMLDivElement> {
  /** Inset role. Default 'md' (--inset-surface, 16). */
  padding?: InsetPadding;
  /** Which edges take the inset. Default 'both' (every side). */
  axis?: InsetAxis;
  children: ReactNode;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Inset({
  padding = 'md',
  axis = 'both',
  className,
  children,
  ...props
}: InsetProps) {
  return (
    <div className={cn('ui-inset', `is-${padding}`, `is-axis-${axis}`, className)} {...props}>
      {children}
    </div>
  );
}
