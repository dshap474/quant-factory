/**
 * Text with marked matches: a search snippet whose matches are delimited by marker
 * characters (by default U+0002 and U+0003, as SQLite's `snippet()` can emit) renders each
 * match in a `mark`, so a host never builds markup from server text.
 *
 * USAGE:
 *   <HighlightedText text={'…the \u0002Kelly\u0003 criterion…'} />
 *   <HighlightedText text="a [b] c" start="[" end="]" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ComponentPropsWithRef } from 'react';

import { cn } from '../lib/cn';

import './HighlightedText.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface HighlightedTextProps extends Omit<ComponentPropsWithRef<'span'>, 'children'> {
  text: string;
  /** Opens a match. Default U+0002. */
  start?: string;
  /** Closes a match. Default U+0003. */
  end?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function HighlightedText({
  text,
  start = '\u0002',
  end = '\u0003',
  className,
  ...props
}: HighlightedTextProps) {
  // Every piece after the first opens with a match: "match<end>rest".
  const [lead, ...pieces] = text.split(start);
  return (
    <span className={cn('ui-highlighted-text', className)} {...props}>
      {lead}
      {pieces.map((piece, index) => {
        const close = piece.indexOf(end);
        const match = close === -1 ? piece : piece.slice(0, close);
        const rest = close === -1 ? '' : piece.slice(close + end.length);
        return (
          // Pieces are positional and never reorder.
          <span key={index}>
            <mark>{match}</mark>
            {rest}
          </span>
        );
      })}
    </span>
  );
}
