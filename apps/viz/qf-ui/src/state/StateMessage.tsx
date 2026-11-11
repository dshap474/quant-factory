/**
 * Compact shared loading, empty, and error message for constrained regions.
 *
 * USAGE:
 *   <StateMessage state="loading">Loading versions…</StateMessage>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import './StateMessage.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface StateMessageProps {
  state?: 'empty' | 'error' | 'loading';
  children: ReactNode;
  compact?: boolean;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function StateMessage({
  state = 'empty',
  children,
  compact = false,
  className,
}: StateMessageProps) {
  return (
    <div
      className={[
        'ui-state-message',
        `ui-state-message-${state}`,
        compact ? 'ui-state-message-compact' : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      role={state === 'error' ? 'alert' : 'status'}
    >
      {children}
    </div>
  );
}
