/**
 * Empty list / missing data placeholder.
 *
 * USAGE:
 *   <EmptyState title="No signals" hint="Run signal generation" />
 *   <EmptyState title="No signals" align="center" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { cn } from '../lib/cn';
import './EmptyState.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface EmptyStateProps {
  title: string;
  hint?: string | undefined;
  /** Text alignment inside the state box. Default 'start'. */
  align?: 'start' | 'center';
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function EmptyState({ title, hint, align = 'start', className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        'ui-empty-state px-4 py-8',
        align === 'center' ? 'text-center' : 'text-left',
        className,
      )}
    >
      <div className="ui-empty-state-title text-label font-medium text-foreground">{title}</div>
      {hint ? <div className="mt-1 text-caption text-muted-foreground">{hint}</div> : null}
    </div>
  );
}
