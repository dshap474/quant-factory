/**
 * Prose container for rendered markdown / long-form text.
 *
 * Owns the `.prose-dark` recipe and the `.prose-measure` fluid document column (Prose.css).
 * Consumers that still pass the class name directly keep working; new code renders <Prose>.
 *
 * USAGE:
 *   <Prose>{markdownNodes}</Prose>
 *   <Prose as="article" measure ref={articleRef} />
 *   <Prose as="article" measure layout="index" />  // a back-of-book index in columns
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ElementType, HTMLAttributes, Ref } from 'react';

import { cn } from '../lib/cn';

import './Prose.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type ProseLayout = 'flow' | 'index';

export interface ProseProps extends HTMLAttributes<HTMLElement> {
  as?: ElementType;
  /** Fill the available document width; contain images and wrap long tokens. */
  measure?: boolean;
  /** `index` sets a back-of-book index: compact entries flowing in columns. */
  layout?: ProseLayout;
  ref?: Ref<HTMLElement>;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Prose({
  as: Tag = 'div',
  measure = false,
  layout = 'flow',
  className,
  children,
  ...rest
}: ProseProps) {
  return (
    <Tag
      className={cn(
        'prose-dark',
        measure && 'prose-measure',
        layout === 'index' && 'prose-index',
        className,
      )}
      {...rest}
    >
      {children}
    </Tag>
  );
}
