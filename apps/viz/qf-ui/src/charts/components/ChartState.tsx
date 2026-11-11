/**
 * In-frame chart status: the loading, error or empty state a chart frame shows
 * instead of a plot.
 *
 * USAGE:
 *   <TimeSeriesChart title="Price history">
 *     <ChartState status="loading" message="Loading series" />
 *   </TimeSeriesChart>
 *   <ChartState status="error" message="Source unavailable" action={<button …>Retry</button>} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import './ChartState.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ChartStateProps {
  status: 'loading' | 'error' | 'empty';
  /** Shown for error/empty; loading shows the skeleton and uses message only as the accessible label. */
  message?: string;
  /** e.g. a retry control (the host passes its own button component). */
  action?: ReactNode;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ChartState({ status, message, action, className }: ChartStateProps) {
  const classes = ['qf-chart-state', className ?? ''].filter(Boolean).join(' ');

  if (status === 'loading') {
    return (
      <div className={classes} data-status="loading" role="status" aria-label={message}>
        <div className="qf-chart-state-skeleton" aria-hidden="true" />
        {action}
      </div>
    );
  }

  const body = (
    <>
      {message ? <span className="qf-chart-state-message">{message}</span> : null}
      {action}
    </>
  );

  if (status === 'error') {
    return (
      <div className={classes} data-status="error" role="alert">
        {body}
      </div>
    );
  }

  return (
    <div className={classes} data-status="empty" role="status">
      {body}
    </div>
  );
}
