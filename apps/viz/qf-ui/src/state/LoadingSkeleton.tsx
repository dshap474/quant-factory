/**
 * Shared, geometry-stable loading placeholders for query-backed regions.
 *
 * USAGE:
 *   <LoadingSkeleton variant="card" count={3} />
 *   <LoadingSkeleton variant="chart" announce={false} />
 *   <LoadingSkeleton variant="segmented" announce={false} />   // a segmented row whose options load
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { QF_CHART_ASPECT_RATIO } from '../charts/core/geometry';
import { cn } from '../lib/cn';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface LoadingSkeletonProps {
  variant?: 'card' | 'chart' | 'line' | 'segmented' | 'table';
  count?: number;
  announce?: boolean;
  label?: string;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function LoadingSkeleton({
  variant = 'line',
  count = 1,
  announce = true,
  label = 'Loading content',
  className,
}: LoadingSkeletonProps) {
  const items = Array.from({ length: count }, (_, i) => i);
  const accessibilityProps = announce
    ? ({ role: 'status', 'aria-label': label } as const)
    : ({ 'aria-hidden': true } as const);
  if (variant === 'table') {
    return (
      <div
        className={cn(
          'overflow-hidden rounded-surface bg-secondary/40 motion-safe:animate-pulse',
          className,
        )}
        {...accessibilityProps}
      >
        <div className="grid h-8 grid-cols-4 gap-4 border-b border-border-subtle bg-secondary/40 px-3 py-2">
          {Array.from({ length: 4 }, (_, index) => (
            <span key={index} className="rounded-badge bg-secondary" />
          ))}
        </div>
        {items.map((item) => (
          <div
            key={item}
            className="grid h-8 grid-cols-4 gap-4 border-b border-border-subtle px-3 py-2 last:border-b-0"
          >
            {Array.from({ length: 4 }, (_, index) => (
              <span key={index} className="rounded-badge bg-secondary/60" />
            ))}
          </div>
        ))}
      </div>
    );
  }
  if (variant === 'chart') {
    return (
      <div
        className={cn('rounded-surface bg-secondary/40 motion-safe:animate-pulse', className)}
        style={{ aspectRatio: `${QF_CHART_ASPECT_RATIO} / 1` }}
        {...accessibilityProps}
      />
    );
  }
  if (variant === 'segmented') {
    // A SegmentedControl's track: one control height plus its 1.5-step inset on each side.
    return (
      <div
        className={cn('rounded-control bg-secondary/40 motion-safe:animate-pulse', className)}
        style={{ height: 'calc(var(--control-height) + 3 * var(--space-1))' }}
        {...accessibilityProps}
      />
    );
  }
  if (variant === 'card') {
    return (
      <div
        className={cn(
          'grid grid-cols-[repeat(auto-fill,minmax(11rem,1fr))] gap-3 motion-safe:animate-pulse',
          className,
        )}
        {...accessibilityProps}
      >
        {items.map((i) => (
          <div key={i} className="h-24 rounded-surface bg-secondary/40" />
        ))}
      </div>
    );
  }
  return (
    <div className={cn('space-y-2 motion-safe:animate-pulse', className)} {...accessibilityProps}>
      {items.map((i) => (
        <div key={i} className="h-4 rounded-badge bg-secondary/60" />
      ))}
    </div>
  );
}
