/**
 * StageBar: one thin segmented track for a pipeline run, one segment per stage, colored
 * by status tone and widened by weight (elapsed seconds, say). Each segment's label and
 * detail sit on hover and in the accessible name.
 *
 * USAGE:
 *   <StageBar
 *     label="Run stages"
 *     segments={[
 *       { id: 'extract', label: 'Extract', tone: 'success', weight: 120, detail: '2m · 14 steps' },
 *       { id: 'audit', label: 'Audit', tone: 'running', weight: 30 },
 *     ]}
 *   />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { cn } from '../lib/cn';
import type { StatusTone } from '../state/Status';

import './StageBar.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface StageBarSegment {
  id: string;
  label: string;
  tone: StatusTone;
  /** Relative width; non-positive or missing weights share a small minimum. */
  weight?: number | null;
  detail?: string;
}

export interface StageBarProps {
  segments: readonly StageBarSegment[];
  /** Accessible name for the whole bar. */
  label: string;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function StageBar({ segments, label, className }: StageBarProps) {
  const total = segments.reduce((sum, item) => sum + Math.max(0, item.weight ?? 0), 0);
  // Every stage stays visible: none falls below 6% of the track.
  const floor = total > 0 ? total * 0.06 : 1;
  return (
    <ol className={cn('ui-stage-bar', className)} aria-label={label}>
      {segments.map((item) => {
        const text = item.detail ? `${item.label} · ${item.detail}` : item.label;
        return (
          <li
            key={item.id}
            aria-label={text}
            title={text}
            className={cn('ui-stage-bar-segment', `is-${item.tone}`)}
            style={{ flexGrow: Math.max(floor, item.weight ?? 0) }}
          />
        );
      })}
    </ol>
  );
}
