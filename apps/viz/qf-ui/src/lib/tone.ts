/**
 * The one status vocabulary for every qf-ui `tone` prop, plus class maps onto
 * the tone token families in styles/tokens.css.
 *
 * USAGE:
 *   import { toneTextClass, type Tone } from '@quant-factory/qf-ui';
 *   <span className={toneTextClass(change >= 0 ? 'success' : 'critical')} />
 *   <div className={toneSurfaceClass('warning')}>…</div>
 *   <Badge tone={statusTone(run.status)}>{run.status}</Badge>
 */

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'critical';

export const TONES: readonly Tone[] = ['neutral', 'info', 'success', 'warning', 'critical'];

// --------------------------------------------------------------------------- #
// Class maps
// --------------------------------------------------------------------------- #

const TEXT: Record<Tone, string> = {
  neutral: 'text-tone-neutral',
  info: 'text-tone-info',
  success: 'text-tone-success',
  warning: 'text-tone-warning',
  critical: 'text-tone-critical',
};

const SURFACE: Record<Tone, string> = {
  neutral: 'bg-tone-neutral-surface border-tone-neutral-border text-tone-neutral',
  info: 'bg-tone-info-surface border-tone-info-border text-tone-info',
  success: 'bg-tone-success-surface border-tone-success-border text-tone-success',
  warning: 'bg-tone-warning-surface border-tone-warning-border text-tone-warning',
  critical: 'bg-tone-critical-surface border-tone-critical-border text-tone-critical',
};

export function toneTextClass(tone: Tone = 'neutral'): string {
  return TEXT[tone];
}

/** Tinted surface + tone border + tone text; add `border` yourself where a box is wanted. */
export function toneSurfaceClass(tone: Tone = 'neutral'): string {
  return SURFACE[tone];
}

/** Sign of a number as a tone: >0 success, <0 critical, 0/NaN/null neutral. */
export function signTone(value: number | null | undefined): Tone {
  if (value === null || value === undefined || Number.isNaN(value) || value === 0) return 'neutral';
  return value > 0 ? 'success' : 'critical';
}

// --------------------------------------------------------------------------- #
// Status tones
// --------------------------------------------------------------------------- #

/** Normalize a status string to a STATUS_TONES key: trimmed, lower case, spaces and hyphens as `_`. */
export function normalizeStatus(status: string): string {
  return status
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_');
}

function statusEntries(tone: Tone, statuses: readonly string[]): [string, Tone][] {
  return statuses.map((status) => [status, tone]);
}

/** The one status-to-tone map. Keys are normalized; anything unlisted is neutral. */
export const STATUS_TONES: Readonly<Record<string, Tone>> = Object.freeze(
  Object.fromEntries([
    ...statusEntries('success', [
      'supported',
      'succeeded',
      'completed',
      'complete',
      'success',
      'baseline',
      'promoted',
      'healthy',
      'live',
      'ok',
      'updated',
      'passing',
      'enabled',
    ]),
    ...statusEntries('info', [
      'descriptive',
      'running',
      'starting',
      'checking',
      'delayed',
      'recovering',
    ]),
    ...statusEntries('neutral', [
      'not_tested',
      'candidate',
      'queued',
      'pending',
      'registered',
      'published',
      'unchanged',
      'unknown',
      'offline',
      'paused',
      'stopped',
      'skipped',
      'cancelled',
      'never',
      'monitored',
      'not_monitored',
      'unregistered',
      'disabled',
      'idle',
    ]),
    ...statusEntries('warning', [
      'inconclusive',
      'warning',
      'stale',
      'partial',
      'unavailable',
      'degraded',
      'missing',
      'attention',
      'incomplete',
    ]),
    ...statusEntries('critical', [
      'falsified',
      'failed',
      'failure',
      'error',
      'rejected',
      'invalidated',
      'interrupted',
      'unresponsive',
      'failing',
      'breach',
      'expired',
      'wrong_schema',
    ]),
  ]),
);

/** Tone for the exact status text shown; empty, null, undefined or unknown input is neutral. */
export function statusTone(status: string | null | undefined): Tone {
  if (!status) return 'neutral';
  return STATUS_TONES[normalizeStatus(status)] ?? 'neutral';
}
