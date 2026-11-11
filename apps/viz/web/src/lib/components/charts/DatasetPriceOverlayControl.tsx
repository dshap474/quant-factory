/**
 * Price overlay selector for dataset multi-series charts, laid out like the
 * cell's Left/Right metric fields.
 *
 * USAGE:
 *   <DatasetPriceOverlayControl options={…} selection="none" onChange={set} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useId } from 'react';
import { Field, LoadingSkeleton, SelectControl, StatusBadge } from '@/ui';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface PriceOverlayOption {
  value: string;
  label: string;
}

export interface DatasetPriceOverlayControlProps {
  options: PriceOverlayOption[];
  selection: string;
  loading?: boolean;
  error?: string | null;
  onChange?: (value: string) => void;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function DatasetPriceOverlayControl({
  options,
  selection,
  loading = false,
  error = null,
  onChange,
}: DatasetPriceOverlayControlProps) {
  const controlId = useId();

  if (!options.length) return null;

  return (
    <Field label="Overlay" htmlFor={controlId} layout="inline">
      <SelectControl
        id={controlId}
        ariaLabel="Overlay"
        value={selection}
        onValueChange={onChange}
        options={options}
      />
      {loading ? <LoadingSkeleton announce={false} className="w-8" /> : null}
      {error ? <StatusBadge tone="critical">{error}</StatusBadge> : null}
    </Field>
  );
}
