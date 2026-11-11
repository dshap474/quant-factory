/**
 * Identifier: the one mono surface for ids, hashes and paths, with end or middle
 * truncation so long run ids never push a layout. The full value is always on `title`,
 * and middle truncation keeps it for assistive tech in a visually hidden span. Middle
 * truncation is the standard `truncateMiddle` (8 leading, 6 trailing characters).
 *
 * USAGE:
 *   <Identifier value="20260101T120000000000Z-v001-00000001" />
 *   <Identifier value={sha} truncate="middle" />
 *   <Identifier value={path} truncate="none" />
 *   <Identifier value={run.id} truncate="middle" copyable />   // trailing copy control
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Check, Copy } from 'lucide-react';
import { useEffect, useState } from 'react';

import { cn } from '../lib/cn';
import { isMiddleTruncated, truncateMiddle } from '../lib/truncate';
import { Button } from './Button';

import './Identifier.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type IdentifierTruncate = 'none' | 'end' | 'middle';

export interface IdentifierProps {
  value: string;
  /** `end` (default) ellipsizes with CSS; `middle` keeps the head and tail. */
  truncate?: IdentifierTruncate;
  /** Add a copy-to-clipboard control after the value. */
  copyable?: boolean;
  className?: string;
}

export interface CopyButtonProps {
  value: string;
  /** Accessible name; default "Copy". */
  label?: string;
  /** `plain` (default) is the inline xs icon beside an id; `control` sits in a toolbar. */
  variant?: 'plain' | 'control';
  /** Runs after the clipboard write succeeds (e.g. a confirmation toast). */
  onCopied?: (value: string) => void;
  /** Runs when the clipboard write fails or the Clipboard API is unavailable. */
  onCopyError?: (value: string) => void;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

/** Icon control that copies `value` and confirms with a check for a moment. */
export function CopyButton({
  value,
  label = 'Copy',
  variant = 'plain',
  onCopied,
  onCopyError,
}: CopyButtonProps) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1200);
    return () => window.clearTimeout(timer);
  }, [copied]);
  const Icon = copied ? Check : Copy;
  return (
    <Button
      variant={variant}
      {...(variant === 'plain' ? { size: 'xs' as const } : {})}
      icon
      className={cn(variant === 'plain' && 'ui-copy-button')}
      aria-label={copied ? 'Copied' : label}
      title={copied ? 'Copied' : label}
      onClick={(event) => {
        event.stopPropagation();
        const write = navigator.clipboard?.writeText(value);
        if (!write) {
          onCopyError?.(value);
          return;
        }
        void write.then(
          () => {
            setCopied(true);
            onCopied?.(value);
          },
          () => onCopyError?.(value),
        );
      }}
    >
      <Icon aria-hidden="true" {...(variant === 'plain' ? { size: 12 } : {})} />
    </Button>
  );
}

export function Identifier({
  value,
  truncate = 'end',
  copyable = false,
  className,
}: IdentifierProps) {
  if (copyable) {
    return (
      <span className={cn('ui-identifier-copy', className)}>
        <Identifier value={value} truncate={truncate} />
        <CopyButton value={value} label="Copy ID" />
      </span>
    );
  }
  const classes = cn('ui-identifier', truncate === 'end' && 'is-truncate-end', className);
  if (truncate === 'middle' && isMiddleTruncated(value)) {
    return (
      <span className={classes} title={value}>
        <span aria-hidden="true">{truncateMiddle(value)}</span>
        <span className="sr-only">{value}</span>
      </span>
    );
  }
  return (
    <span className={classes} title={value}>
      {value}
    </span>
  );
}
