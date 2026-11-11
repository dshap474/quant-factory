/**
 * Preformatted code block.
 *
 * USAGE:
 *   <CodeBlock value={JSON.stringify(config, null, 2)} />
 *   <CodeBlock value={text} className="mt-3" />
 *   <CodeBlock value={command} wrap />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { cn } from '../lib/cn';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface CodeBlockProps {
  value: string;
  /** Wrap long lines (a shell command) instead of scrolling sideways. */
  wrap?: boolean;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function CodeBlock({ value, wrap = false, className }: CodeBlockProps) {
  return (
    <pre
      className={cn(
        'overflow-x-auto rounded-surface border border-border bg-background p-3 font-mono text-caption text-foreground',
        wrap && 'whitespace-pre-wrap break-all',
        className,
      )}
    >
      {value}
    </pre>
  );
}
