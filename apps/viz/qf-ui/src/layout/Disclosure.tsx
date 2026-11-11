/**
 * Native disclosure (`<details>`) with the shared summary row: chevron, title, optional meta.
 *
 * USAGE:
 *   <Disclosure summary="config.json"><CodeBlock value={json} /></Disclosure>
 *   <Disclosure summary="Structure details" meta="1,440 bars · 12 markers" variant="row" defaultOpen>…</Disclosure>
 *   <Disclosure summary="Advanced" open={open} onToggle={setOpen} lazy>…</Disclosure> // controlled; content mounts on open
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { ChevronRight } from 'lucide-react';
import { type ComponentPropsWithRef, type ReactNode, useState } from 'react';
import { cn } from '../lib/cn';
import { ICON_SIZE_SM, ICON_STROKE } from '../lib/icon';

import './Disclosure.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface DisclosureProps
  extends Omit<ComponentPropsWithRef<'details'>, 'open' | 'onToggle' | 'children'> {
  /** Summary row title. */
  summary: ReactNode;
  /** Secondary text at the end of the summary row (counts, ids). */
  meta?: ReactNode;
  /** Uncontrolled initial state. */
  defaultOpen?: boolean;
  /** Controlled state; pair with onToggle. */
  open?: boolean;
  onToggle?: (open: boolean) => void;
  /** Mount children only while open. */
  lazy?: boolean;
  /** `row`: divider row inside a panel (top rule). */
  variant?: 'plain' | 'row';
  children: ReactNode;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Disclosure({
  summary,
  meta,
  defaultOpen = false,
  open,
  onToggle,
  lazy = false,
  variant = 'plain',
  className,
  children,
  ...props
}: DisclosureProps) {
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const isOpen = open ?? internalOpen;
  return (
    <details
      className={cn('ui-disclosure', variant === 'row' && 'is-row', className)}
      open={isOpen}
      onToggle={(event) => {
        const next = event.currentTarget.open;
        if (open === undefined) setInternalOpen(next);
        onToggle?.(next);
      }}
      {...props}
    >
      <summary className="ui-disclosure-summary">
        <ChevronRight
          className="ui-disclosure-chevron"
          aria-hidden="true"
          size={ICON_SIZE_SM}
          strokeWidth={ICON_STROKE}
        />
        <span className="ui-disclosure-title">{summary}</span>
        {meta !== undefined && meta !== null ? (
          <span className="ui-disclosure-meta">{meta}</span>
        ) : null}
      </summary>
      {lazy && !isOpen ? null : <div className="ui-disclosure-content">{children}</div>}
    </details>
  );
}
