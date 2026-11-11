/**
 * Shared linear step strip: an ordered list of pipeline stages with a current marker.
 *
 * USAGE:
 *   <StepStrip label="Training stages" current={1} items={[{ id: 'fit', label: 'Fit' }]} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import { cn } from '../lib/cn';

import './StepStrip.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface StepStripItem {
  id: string;
  label: ReactNode;
}

export interface StepStripProps {
  items: readonly StepStripItem[];
  /** Index of the in-flight step; earlier items are complete, later ones upcoming. -1 = none current. */
  current: number;
  /** Accessible name for the ordered list. */
  label: string;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function StepStrip({ items, current, label, className }: StepStripProps) {
  return (
    <ol className={cn('ui-step-strip', className)} aria-label={label}>
      {items.map((item, index) => {
        const state = index < current ? 'complete' : index === current ? 'current' : 'upcoming';
        return (
          <li
            key={item.id}
            className={cn('ui-step-strip-item', `is-${state}`)}
            aria-current={state === 'current' ? 'step' : undefined}
          >
            {item.label}
          </li>
        );
      })}
    </ol>
  );
}
