/**
 * Shared structural surface for bordered, flush, or inset application regions.
 *
 * USAGE:
 *   <Surface padding="md">…</Surface>                       // bordered card
 *   <Surface variant="panel" padding="none">…</Surface>     // flush band: top/bottom rules only
 *   <Surface variant="inset">…</Surface>                    // borderless subtle fill
 *   <Surface as="aside" padding="none" clip>…</Surface>     // clips an inner table or ScrollArea
 *   <Surface variant="panel" padding="gutter" rules="block-end" tinted>…</Surface>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { HTMLAttributes, ReactNode } from 'react';

import { cn } from '../lib/cn';

import './Surface.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type SurfaceVariant = 'card' | 'panel' | 'inset';

export interface SurfaceProps extends HTMLAttributes<HTMLElement> {
  as?: 'aside' | 'div' | 'pre' | 'section';
  padding?: 'none' | 'sm' | 'md' | 'lg' | 'gutter';
  /** card: bordered card; panel: flush band with top/bottom rules; inset: borderless subtle fill. */
  variant?: SurfaceVariant;
  /** Clip overflowing children (tables, scroll areas) to the surface box. */
  clip?: boolean;
  /** variant="panel" only: which hairlines paint. Default 'block' (top + bottom). */
  rules?: 'block' | 'block-end' | 'none';
  /** variant="panel" only: subtle card tint behind the band. */
  tinted?: boolean;
  children: ReactNode;
}

// sm (12) equals --inset-surface-compact, md (16) equals --inset-surface, lg is 24.
const PADDING = {
  none: '',
  sm: 'p-3',
  md: 'p-4',
  lg: 'p-6',
  gutter: 'ui-surface-gutter',
} as const;
const VARIANT = { card: '', panel: 'ui-surface-panel', inset: 'ui-surface-inset' } as const;

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Surface({
  as: Element = 'div',
  padding = 'md',
  variant = 'card',
  clip = false,
  rules = 'block',
  tinted = false,
  className,
  children,
  ...props
}: SurfaceProps) {
  return (
    <Element
      className={cn(
        'ui-surface',
        VARIANT[variant],
        clip && 'ui-surface-clip',
        rules !== 'block' && `is-rules-${rules}`,
        tinted && 'is-tinted',
        PADDING[padding],
        className,
      )}
      {...props}
    >
      {children}
    </Element>
  );
}
