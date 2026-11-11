/**
 * Compact status/meta badge: a 20px soft-filled sans pill (16px at size="sm") that never
 * shrinks. Tone is the shared `Tone` vocabulary; text case is the caller's.
 *
 * USAGE:
 *   <Badge tone="info">lgbm</Badge>
 *   <Badge tone="critical" size="sm">failed</Badge>
 *   <Badge variant="ghost">meta</Badge>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { type Tone, toneTextClass } from '../lib/tone';

import './Badge.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface BadgeProps {
  tone?: Tone;
  size?: 'sm' | 'md';
  variant?: 'solid' | 'ghost';
  className?: string;
  children: React.ReactNode;
}

const BORDER: Record<Tone, string> = {
  neutral: 'border-tone-neutral-border',
  info: 'border-tone-info-border',
  success: 'border-tone-success-border',
  warning: 'border-tone-warning-border',
  critical: 'border-tone-critical-border',
};

const SURFACE_BG: Record<Tone, string> = {
  neutral: 'bg-tone-neutral-surface',
  info: 'bg-tone-info-surface',
  success: 'bg-tone-success-surface',
  warning: 'bg-tone-warning-surface',
  critical: 'bg-tone-critical-surface',
};

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Badge({
  tone = 'neutral',
  size = 'md',
  variant = 'solid',
  className,
  children,
}: BadgeProps) {
  return (
    <span
      className={[
        'ui-badge',
        size === 'sm' && 'is-sm',
        variant === 'ghost'
          ? 'border-transparent text-muted-foreground'
          : `${BORDER[tone]} ${SURFACE_BG[tone]} ${toneTextClass(tone)}`,
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {children}
    </span>
  );
}
