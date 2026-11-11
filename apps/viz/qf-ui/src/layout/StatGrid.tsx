/**
 * Labelled statistic list (`<dl>`) in three arrangements: tiles, a bordered strip, or rows.
 *
 * USAGE:
 *   <StatGrid aria-label="Snapshot">
 *     <StatItem label="Published" value={date} />
 *   </StatGrid>
 *   <StatGrid variant="strip" columns={4}>…</StatGrid> // page-top status band
 *   <StatGrid variant="rows">…</StatGrid>              // label | value lines
 *   <StatGrid variant="inline">…</StatGrid>            // wrapping label value delta strip
 *   <StatGrid variant="strip" columns={4} boxed>…</StatGrid> // card-framed strip
 *   <StatItem label="Cost" value="$12" tone="critical" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ComponentPropsWithRef, ReactNode } from 'react';

import { cn } from '../lib/cn';

import './StatGrid.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type StatGridVariant = 'grid' | 'strip' | 'rows' | 'inline';

export interface StatGridProps extends ComponentPropsWithRef<'dl'> {
  /**
   * grid: label-over-value tiles; strip: bordered band with dividers; rows: label | value
   * lines; inline: wrapping horizontal strip of label value delta readings.
   */
  variant?: StatGridVariant;
  /** Fixed column count for the strip variant; defaults to auto-fit. */
  columns?: 2 | 3 | 4;
  /** Card-framed strip/rows: full border, card fill, and dividers on wrapped rows. */
  boxed?: boolean;
  children: ReactNode;
}

export interface StatItemProps extends Omit<ComponentPropsWithRef<'div'>, 'children'> {
  label: ReactNode;
  value: ReactNode;
  tone?: 'default' | 'success' | 'critical';
  /** Change or secondary reading rendered after the value inside the same <dd>. */
  delta?: ReactNode;
  /** Default 'accent'. */
  deltaTone?: 'accent' | 'positive' | 'negative' | 'muted';
}

// --------------------------------------------------------------------------- #
// Components
// --------------------------------------------------------------------------- #

export function StatGrid({
  variant = 'grid',
  columns,
  boxed = false,
  className,
  children,
  ...props
}: StatGridProps) {
  return (
    <dl
      className={cn(
        'ui-stat-grid',
        `is-${variant}`,
        columns !== undefined && `is-cols-${columns}`,
        boxed && 'is-boxed',
        className,
      )}
      {...props}
    >
      {children}
    </dl>
  );
}

export function StatItem({
  label,
  value,
  tone = 'default',
  delta,
  deltaTone,
  className,
  ...props
}: StatItemProps) {
  return (
    <div className={cn('ui-stat-item', className)} {...props}>
      <dt className="ui-stat-label">{label}</dt>
      <dd className={cn('ui-stat-value', tone !== 'default' && `is-${tone}`)}>
        {value}
        {delta == null ? null : (
          <span className={cn('ui-stat-delta', `is-${deltaTone ?? 'accent'}`)}>{delta}</span>
        )}
      </dd>
    </div>
  );
}
