/**
 * Shared determinate progress bar: one track, one fill, the ARIA contract included.
 *
 * USAGE:
 *   <ProgressBar value={7} max={15} label="Completed validation fits" />
 *   <ProgressBar value={0} max={null} label="Completed validation fits" />
 *   <ProgressBar value={13} max={874} label="Coins" tone="info" size="md" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { cn } from '../lib/cn';

import './ProgressBar.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ProgressBarProps {
  /** Completed amount. */
  value: number;
  /** Upper bound; null/undefined leaves the bar empty and drops aria-valuemax. */
  max?: number | null;
  /** Accessible name; the bar owns role="progressbar". */
  label: string;
  /** Fill colour; `neutral` (default) is the muted foreground. */
  tone?: 'neutral' | 'info' | 'success' | 'warning' | 'critical';
  /** `sm` (default) is a hairline track; `md` a rounded bar for a headline figure. */
  size?: 'sm' | 'md';
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ProgressBar({
  value,
  max,
  label,
  tone = 'neutral',
  size = 'sm',
  className,
}: ProgressBarProps) {
  const percent = max && max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div
      className={cn('ui-progress-bar', `is-${tone}`, size === 'md' && 'is-md', className)}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={max ?? undefined}
      aria-valuenow={value}
      aria-label={label}
    >
      <span className="ui-progress-bar-fill" style={{ width: `${percent}%` }} />
    </div>
  );
}
