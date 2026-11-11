/**
 * TokenUsage: one compact line of provider-reported token counts
 * (`In 2.3k · Out 269 · Cache 1.2k · Reason 136`). Missing and zero counts are hidden;
 * exact values and their provenance sit on hover.
 *
 * USAGE:
 *   <TokenUsage input={step.input_tokens} output={step.output_tokens} cacheRead={step.cache_read_tokens} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { cn } from '../lib/cn';
import { EMPTY, formatCompact } from '../lib/number-format';

import './TokenUsage.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface TokenUsageProps {
  input?: number | null | undefined;
  output?: number | null | undefined;
  cacheRead?: number | null | undefined;
  cacheWrite?: number | null | undefined;
  reasoning?: number | null | undefined;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function TokenUsage({
  input,
  output,
  cacheRead,
  cacheWrite,
  reasoning,
  className,
}: TokenUsageProps) {
  const counts: [string, number | null | undefined][] = [
    ['In', input],
    ['Out', output],
    ['Cache', cacheRead],
    ['Cache write', cacheWrite],
    ['Reason', reasoning],
  ];
  const parts = counts.filter(
    (part): part is [string, number] => typeof part[1] === 'number' && part[1] > 0,
  );
  if (parts.length === 0) {
    return <span className={cn('ui-token-usage', className)}>{EMPTY}</span>;
  }
  const exact = parts.map(([name, value]) => `${name} ${value.toLocaleString('en-US')}`);
  return (
    <span
      className={cn('ui-token-usage', className)}
      title={`Provider-reported tokens · ${exact.join(' · ')}`}
    >
      {parts.map(([name, value]) => `${name} ${formatCompact(value)}`).join(' · ')}
    </span>
  );
}
