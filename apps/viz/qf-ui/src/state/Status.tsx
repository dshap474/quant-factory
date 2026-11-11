/**
 * Status indicators: a tone-colored dot and a dot-plus-label badge.
 *
 * Tones: the shared `Tone` vocabulary (neutral, info, success, warning, critical) plus
 * `running` (primary, pulsing).
 *
 * USAGE:
 *   <StatusDot tone="running" label="Running" />
 *   <StatusBadge tone="success">completed</StatusBadge>
 *   <StatusBadge tone="critical" dot={false}>failed</StatusBadge>
 *   <StatusBadge tone="success" bordered dot={false}>completed</StatusBadge>
 *   <StatusBadge status={run.status}>{run.status}</StatusBadge>   // tone via statusTone()
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import { cn } from '../lib/cn';
import { normalizeStatus, statusTone, type Tone, toneTextClass } from '../lib/tone';

import './Status.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

/** Shared `Tone` plus `running` (primary, pulsing). */
export type StatusTone = Tone | 'running';

export interface StatusDotProps {
  tone?: StatusTone;
  /** Accessible name; without it the dot is decorative (aria-hidden). */
  label?: string;
  className?: string;
}

export interface StatusBadgeProps {
  /** Explicit tone; when absent, derived from `status` (else neutral). */
  tone?: StatusTone;
  /** Raw status string: sets `data-status` and, without `tone`, the tone via `statusTone()`.
      Children still render as given. */
  status?: string;
  /** Hide the leading dot. */
  dot?: boolean;
  /** Outline the badge with a tone-matched hairline box. */
  bordered?: boolean;
  className?: string;
  children: ReactNode;
}

const LIVE_STATUSES: ReadonlySet<string> = new Set(['running', 'starting', 'checking']);

/** `statusTone()` for live work: an in-flight status (running, starting, checking) is the
    pulsing `running` tone; every other status maps exactly as `statusTone()` maps it. */
export function liveStatusTone(status: string | null | undefined): StatusTone {
  if (status && LIVE_STATUSES.has(normalizeStatus(status))) return 'running';
  return statusTone(status);
}

function statusTextClass(tone: StatusTone): string {
  return tone === 'running' ? toneTextClass('info') : toneTextClass(tone);
}

// --------------------------------------------------------------------------- #
// Components
// --------------------------------------------------------------------------- #

export function StatusDot({ tone = 'neutral', label, className }: StatusDotProps) {
  const classes = cn('ui-status-dot', `is-${tone}`, className);
  if (label) {
    return <span className={classes} role="img" aria-label={label} title={label} />;
  }
  return <span className={classes} aria-hidden="true" />;
}

export function StatusBadge({
  tone: toneProp,
  status,
  dot = true,
  bordered = false,
  className,
  children,
}: StatusBadgeProps) {
  const tone: StatusTone = toneProp ?? (status === undefined ? 'neutral' : statusTone(status));
  return (
    <span
      className={cn(
        'ui-status-badge',
        `is-${tone}`,
        bordered && 'is-bordered',
        'inline-flex flex-none items-center gap-1 whitespace-nowrap',
        statusTextClass(tone),
        className,
      )}
      data-status={status === undefined ? undefined : normalizeStatus(status)}
    >
      {dot ? <StatusDot tone={tone} /> : null}
      <span>{children}</span>
    </span>
  );
}
