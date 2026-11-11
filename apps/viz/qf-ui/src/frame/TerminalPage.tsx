/**
 * Terminal detail-page frame: edge-to-edge header band (title, optional subtitle,
 * right-side machine facts) over a scrollable padded body of hairline sections.
 *
 * USAGE:
 *   <TerminalPage title="example-trend" subtitle="Strategy family" right="3 versions">
 *     <TerminalSection title="preset results">…</TerminalSection>
 *   </TerminalPage>
 *   <TerminalPage title="Agents" tabs={<SegmentedControl variant="tabs" … />}>…</TerminalPage>
 *   <TerminalPage title="Example" tabs={…} toolbar={<Field label="Date" …/>}>…</TerminalPage>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { cn } from '../lib/cn';

import { PageHeader } from './PageHeader';
import './TerminalPage.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface TerminalPageProps {
  title: string;
  kicker?: string;
  subtitle?: ReactNode;
  /** Status badges set beside the title. */
  badges?: ReactNode;
  right?: ReactNode;
  /** The page's view tabs; they lead the header and the title moves right (PageHeader). */
  tabs?: ReactNode;
  /** A back control set before the title (PageHeader). */
  back?: ReactNode;
  /** Page-wide controls (observation day, scope): one right-aligned row that opens the body,
      one block gap above the content it governs. Section-local filters stay in their section. */
  toolbar?: ReactNode;
  /** Body is a bounded flex column with no padding; the child owns its overflow. */
  fill?: boolean;
  className?: string;
  children: ReactNode;
}

export interface TerminalSectionProps {
  title: string;
  /** Heading id; also wires the section's `aria-labelledby`. */
  id?: string;
  right?: ReactNode;
  /** Fill a bounded flex-column host: the section is a flex column and its body region flexes. */
  fill?: boolean;
  className?: string;
  children: ReactNode;
}

// --------------------------------------------------------------------------- #
// Components
// --------------------------------------------------------------------------- #

export function TerminalPage({
  title,
  kicker,
  subtitle,
  badges,
  right,
  tabs,
  back,
  toolbar,
  fill = false,
  className,
  children,
}: TerminalPageProps) {
  return (
    <div className={cn('terminal-page', fill && 'is-fill', className)}>
      <PageHeader
        {...(kicker === undefined ? {} : { kicker })}
        title={title}
        subtitle={subtitle}
        badges={badges}
        right={right ? <div className="terminal-page-facts">{right}</div> : null}
        tabs={tabs}
        back={back}
      />
      <div className={cn('terminal-page-body', fill && 'is-fill')}>
        {toolbar ? <div className="terminal-page-toolbar">{toolbar}</div> : null}
        {children}
      </div>
    </div>
  );
}

export function TerminalSection({
  title,
  id,
  right,
  fill = false,
  className,
  children,
}: TerminalSectionProps) {
  return (
    <section className={cn('terminal-section', fill && 'is-fill', className)} aria-labelledby={id}>
      <div className="terminal-section-head">
        <h2 id={id}>{title}</h2>
        {right ? <span className="terminal-section-right">{right}</span> : null}
      </div>
      {children}
    </section>
  );
}
