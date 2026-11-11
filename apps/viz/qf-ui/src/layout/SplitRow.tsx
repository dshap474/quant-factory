/**
 * A main column beside a docked aside (a rail), filling a bounded host.
 *
 * USAGE:
 *   <SplitRow aside={<Rail />}>…</SplitRow>
 *   <SplitRow as="section" fill aria-label="Workspace" asideSide="start" aside={<Rail />}>…</SplitRow>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import { cn } from '../lib/cn';

import './SplitRow.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface SplitRowProps {
  /** Docked side column, rendered after the main column ('end', default) or before it. */
  aside?: ReactNode;
  asideSide?: 'start' | 'end';
  /** Fill the bounded parent. */
  fill?: boolean;
  as?: 'div' | 'section';
  'aria-label'?: string;
  className?: string;
  children: ReactNode;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function SplitRow({
  aside,
  asideSide = 'end',
  fill,
  as: Tag = 'div',
  'aria-label': ariaLabel,
  className,
  children,
}: SplitRowProps) {
  return (
    <Tag className={cn('ui-split-row', fill && 'is-fill', className)} aria-label={ariaLabel}>
      {asideSide === 'start' ? aside : null}
      <div className="ui-split-row-main">{children}</div>
      {asideSide === 'end' ? aside : null}
    </Tag>
  );
}
