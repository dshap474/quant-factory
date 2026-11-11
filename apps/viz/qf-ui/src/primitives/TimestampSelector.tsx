/**
 * Date/timestamp dropdown for point-in-time pickers.
 *
 * USAGE:
 *   <TimestampSelector timestamps={dates} value={date} onChange={setDate} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useId } from 'react';

import { Field } from './Field';
import { SelectControl } from './Select';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface TimestampSelectorProps {
  timestamps: string[];
  value: string | null;
  onChange: (value: string) => void;
  label?: string;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function fmt(ts: string): string {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function TimestampSelector({
  timestamps,
  value,
  onChange,
  label = 'Timestamp',
}: TimestampSelectorProps) {
  const controlId = useId();

  if (timestamps.length <= 1) return null;

  return (
    <Field label={label} htmlFor={controlId} layout="inline">
      <SelectControl
        id={controlId}
        size="sm"
        value={value ?? ''}
        onValueChange={onChange}
        options={timestamps.map((timestamp) => ({ value: timestamp, label: fmt(timestamp) }))}
      />
    </Field>
  );
}
