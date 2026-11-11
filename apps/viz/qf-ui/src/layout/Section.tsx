/**
 * Vertical page section with optional title.
 *
 * USAGE:
 *   <Section title="Recent">…</Section>
 *   <Section title="Recent" className="min-w-0">…</Section>
 *   <Section title="Matrix" actions={<SegmentedControl … />}>…</Section> // control beside the heading
 *
 * Stacked siblings own their own uniform gap (`.ui-section + .ui-section`), so a
 * caller className never removes it.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import { cn } from '../lib/cn';

import './Section.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface SectionProps {
  title?: string;
  /** Controls aligned beside the heading (e.g. a view switch); wraps below on narrow widths. */
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Section({ title, actions, className, children }: SectionProps) {
  const heading = title ? <h2 className="section-heading">{title}</h2> : null;
  return (
    <section className={cn('ui-section', className)}>
      {actions ? (
        <div className="ui-section-header">
          {heading}
          {actions}
        </div>
      ) : (
        heading
      )}
      {children}
    </section>
  );
}
