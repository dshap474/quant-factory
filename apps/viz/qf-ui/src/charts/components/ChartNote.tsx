/**
 * Small provenance or status note for a chart header: the model behind a line, a source
 * label, the current reading.
 *
 * USAGE:
 *   <TimeSeriesChart headerRight={<ChartNote>holdout from 2025-01-01</ChartNote>} … />
 *   <ChartNote tone="error">Source unavailable</ChartNote>
 *   <ChartNote tone="waiting">Awaiting local data</ChartNote>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import './ChartNote.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ChartNoteProps {
  children: ReactNode;
  tone?: 'default' | 'error' | 'waiting';
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ChartNote({ children, tone = 'default', className }: ChartNoteProps) {
  const classes = ['qf-chart-note', tone === 'default' ? '' : `is-${tone}`, className ?? '']
    .filter(Boolean)
    .join(' ');
  return <span className={classes}>{children}</span>;
}
