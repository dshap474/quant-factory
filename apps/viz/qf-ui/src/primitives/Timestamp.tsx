/**
 * Timestamp: renders an instant in the shared date grammar inside `<time>`, with the
 * precise ISO value on `dateTime` and on hover.
 *
 * USAGE:
 *   <Timestamp value={row.updated_at} />
 *   <Timestamp value={epochMs} precision="date" />
 *   <Timestamp value={iso} timeZone="local" precision="second" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { cn } from '../lib/cn';
import {
  formatTimestamp,
  type TimestampInput,
  type TimestampPrecision,
  type TimestampTimeZone,
  toTimestampDate,
} from '../lib/time-format';

import './Timestamp.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface TimestampProps {
  value: TimestampInput;
  precision?: TimestampPrecision;
  timeZone?: TimestampTimeZone;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Timestamp({ value, precision, timeZone, className }: TimestampProps) {
  const date = toTimestampDate(value);
  const iso = date ? date.toISOString() : undefined;
  return (
    <time className={cn('ui-timestamp', className)} dateTime={iso} title={iso}>
      {formatTimestamp(value, { precision, timeZone })}
    </time>
  );
}
