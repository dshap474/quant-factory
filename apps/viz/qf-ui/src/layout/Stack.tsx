/**
 * Vertical flex stack: the parent owns the space between its children.
 *
 * USAGE:
 *   <Stack gap="stack">…</Stack>      // siblings in a group (--gap-stack, 8)
 *   <Stack gap="block">…</Stack>      // block to block (--gap-block, 16)
 *   <Stack className="min-w-0">…</Stack>
 *   <Stack as="section" aria-label="Results">…</Stack>   // the stack is the landmark
 *
 * Gap names are spacing roles, each mapped to its `--gap-*` token; `xs` (4) is for
 * component internals only. Children carry no outer margins.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { HTMLAttributes, ReactNode } from 'react';

import { cn } from '../lib/cn';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type StackGap = 'none' | 'xs' | 'stack' | 'heading' | 'block' | 'section';

export interface StackProps extends HTMLAttributes<HTMLElement> {
  /** Spacing role between children. Default 'heading' (--gap-heading, 12). */
  gap?: StackGap;
  /** Rendered element. Default 'div'. */
  as?: 'div' | 'section' | 'header' | 'article' | 'aside';
  children: ReactNode;
}

const GAPS: Record<StackGap, string> = {
  none: 'gap-0',
  xs: 'gap-1',
  stack: 'gap-[var(--gap-stack)]',
  heading: 'gap-[var(--gap-heading)]',
  block: 'gap-[var(--gap-block)]',
  section: 'gap-[var(--gap-section)]',
};

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Stack({
  gap = 'heading',
  as: Element = 'div',
  className,
  children,
  ...props
}: StackProps) {
  return (
    <Element className={cn('flex flex-col', GAPS[gap], className)} {...props}>
      {children}
    </Element>
  );
}
