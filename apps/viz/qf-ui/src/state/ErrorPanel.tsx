/**
 * Inline error message (frameless, with a leading alert glyph) and optional retry.
 *
 * USAGE:
 *   <ErrorPanel message={err} onRetry={refetch} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { CircleAlert } from 'lucide-react';

import { cn } from '../lib/cn';
import { ICON_SIZE, ICON_STROKE } from '../lib/icon';
import { Button } from '../primitives/Button';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ErrorPanelProps {
  message: string;
  onRetry?: (() => void) | undefined;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ErrorPanel({ message, onRetry, className }: ErrorPanelProps) {
  return (
    <div
      className={cn(
        'ui-error-panel flex items-start gap-2 px-4 py-3 text-body text-foreground',
        className,
      )}
      role="alert"
    >
      {/* A body-line-high box centres the icon on the first line of the message. */}
      <span className="flex h-5 flex-none items-center">
        <CircleAlert
          aria-hidden="true"
          className="text-tone-critical"
          size={ICON_SIZE}
          strokeWidth={ICON_STROKE}
        />
      </span>
      <div className="min-w-0">
        <div>{message}</div>
        {onRetry ? (
          <Button variant="control" className="mt-2" onClick={onRetry}>
            Retry
          </Button>
        ) : null}
      </div>
    </div>
  );
}
