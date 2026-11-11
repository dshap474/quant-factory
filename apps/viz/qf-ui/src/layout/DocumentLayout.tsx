/**
 * A reading column at prose measure beside a sticky aside that takes the remaining
 * width; the aside drops under the document when the host is too narrow for both.
 *
 * USAGE:
 *   <DocumentLayout aside={<Section title="Record">…</Section>}>
 *     <Section title="Documents"><Prose measure>…</Prose></Section>
 *   </DocumentLayout>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import { cn } from '../lib/cn';

import './DocumentLayout.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface DocumentLayoutProps {
  /** Facts, metadata or navigation read beside the document. */
  aside?: ReactNode;
  className?: string;
  children: ReactNode;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function DocumentLayout({ aside, className, children }: DocumentLayoutProps) {
  return (
    <div className={cn('ui-document-layout', className)}>
      <div className="ui-document-layout-grid">
        <div className="ui-document-layout-main">{children}</div>
        {aside ? <aside className="ui-document-layout-aside">{aside}</aside> : null}
      </div>
    </div>
  );
}
