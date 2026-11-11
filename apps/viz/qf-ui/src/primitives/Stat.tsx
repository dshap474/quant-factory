/**
 * Compact labeled statistic.
 *
 * USAGE:
 *   <Stat label="AUC" value="91.2%" mono />
 *   <Stat label="Cost" value="$12" tone="critical" size="sm" className="shrink-0" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import { cn } from '../lib/cn';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface StatProps {
  label: string;
  value: ReactNode;
  size?: 'sm' | 'md';
  mono?: boolean;
  tone?: 'default' | 'success' | 'critical';
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Stat({
  label,
  value,
  size = 'md',
  mono = false,
  tone = 'default',
  className,
}: StatProps) {
  const toneClass =
    tone === 'success'
      ? 'text-positive'
      : tone === 'critical'
        ? 'text-negative'
        : 'text-foreground';
  return (
    <div className={cn('min-w-0', className)}>
      <div className="font-medium text-muted-foreground text-caption">{label}</div>
      <div
        className={cn(
          'font-semibold tabular-nums',
          toneClass,
          size === 'sm' ? 'text-body' : 'text-section',
          mono && 'font-mono',
        )}
      >
        {value}
      </div>
    </div>
  );
}
