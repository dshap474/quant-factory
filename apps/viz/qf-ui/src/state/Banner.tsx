/**
 * Flush tinted hairline band announcing a data caveat above a workspace pane.
 *
 * Distinct from StateMessage: that is a bordered, padded card carrying
 * loading/empty/error state; this is a one-line notice attached to content.
 * Tone is the shared `Tone` vocabulary; `critical` announces as an alert.
 *
 * USAGE:
 *   <Banner tone="info">3 malformed run sidecars omitted</Banner>
 *   <Banner tone="warning">Feed is stale</Banner>
 *   <Banner tone="critical">Ingest halted</Banner>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import { cn } from '../lib/cn';
import type { Tone } from '../lib/tone';

import './Banner.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface BannerProps {
  tone?: Tone;
  className?: string;
  children: ReactNode;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Banner({ tone = 'info', className, children }: BannerProps) {
  return (
    <div
      className={cn('ui-banner', `is-${tone}`, className)}
      role={tone === 'critical' ? 'alert' : 'status'}
    >
      {children}
    </div>
  );
}
