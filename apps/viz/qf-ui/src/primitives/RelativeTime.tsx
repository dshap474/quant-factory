/**
 * RelativeTime: an instant as its age (`5m ago`) inside `<time>`, with the full local
 * date-time on hover and the ISO value on `dateTime`. The caller owns `now` so a list
 * ticks from one clock.
 *
 * USAGE:
 *   <RelativeTime value={run.started_at} />
 *   <RelativeTime value={run.started_at} now={now} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { cn } from '../lib/cn';
import { formatRelativeTime, formatTimestamp, toTimestampDate } from '../lib/time-format';

import './Timestamp.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface RelativeTimeProps {
  value: string | null | undefined;
  /** Reference instant in epoch ms; defaults to render time. */
  now?: number;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function RelativeTime({ value, now, className }: RelativeTimeProps) {
  const date = value ? toTimestampDate(value) : null;
  return (
    <time
      className={cn('ui-timestamp', className)}
      dateTime={date?.toISOString()}
      title={date ? formatTimestamp(date, { precision: 'second', timeZone: 'local' }) : undefined}
    >
      {formatRelativeTime(value, now)}
    </time>
  );
}
