/**
 * Constrained page content width wrapper that owns the page's vertical rhythm.
 *
 * USAGE:
 *   <PageShell maxWidth="lg">…</PageShell>      // sections, --gap-section apart
 *   <PageShell rhythm="block">…</PageShell>     // dense page of cards, --gap-block apart
 *   <PageShell fill>…</PageShell>   // bounded flex column that hands its height to a fill child
 *
 * Direct children are spaced by the shell; they carry no outer margins of their own.
 * A view switcher placed straight on the page sits one --gap-block above the content it
 * switches. The scrolling pane that hosts the shell supplies the --gap-block top and
 * --inset-page bottom edges, so the shell adds no padding of its own.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { cn } from '../lib/cn';
import './PageShell.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type PageShellRhythm = 'section' | 'block';

export interface PageShellProps {
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
  /** Gap between direct children: 'section' (default, --gap-section) or 'block' (--gap-block) for pages of cards. */
  rhythm?: PageShellRhythm;
  /** Bounded flex column: the page takes the pane height and a fill child (TerminalSection fill / ScrollArea fill) owns the scroll. */
  fill?: boolean;
  className?: string;
  children: ReactNode;
}

const MAX: Record<NonNullable<PageShellProps['maxWidth']>, string> = {
  sm: 'max-w-[900px]',
  md: 'max-w-[1200px]',
  lg: 'max-w-[1400px]',
  xl: 'max-w-[1500px]',
  full: 'max-w-none',
};

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function PageShell({
  maxWidth = 'lg',
  rhythm = 'section',
  fill,
  className,
  children,
}: PageShellProps) {
  return (
    <div
      className={cn(
        'page-shell',
        rhythm === 'block' && 'is-rhythm-block',
        fill && 'is-fill',
        MAX[maxWidth],
        className,
      )}
    >
      {children}
    </div>
  );
}
