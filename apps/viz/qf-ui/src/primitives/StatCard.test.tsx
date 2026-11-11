/**
 * Structural tests for shared stat-card formatting and presentation states.
 *
 * USAGE:
 *   pnpm test -- src/primitives/StatCard.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { StatCard } from './StatCard';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('StatCard', () => {
  it.each([
    { format: 'number' as const, value: 1.234, expected: '1.23' },
    { format: 'number' as const, value: 12345, expected: '12,345' },
    { format: 'percent' as const, value: 0.1234, expected: '12.34%' },
    { format: 'currency' as const, value: 12, expected: '$12' },
    { format: 'raw' as const, value: 1.234, expected: '1.234' },
  ])('formats $format numeric metrics', ({ format, value, expected }) => {
    const markup = renderToStaticMarkup(<StatCard label="Metric" value={value} format={format} />);

    expect(markup).toContain(`>${expected}<`);
  });

  it.each([
    { trend: 'up' as const, tone: 'text-positive' },
    { trend: 'down' as const, tone: 'text-negative' },
    { trend: 'neutral' as const, tone: 'text-foreground' },
  ])('applies the $trend semantic trend tone', ({ trend, tone }) => {
    const markup = renderToStaticMarkup(<StatCard label="Return" value="12%" trend={trend} />);

    expect(markup).toContain(tone);
  });

  it('preserves optional detail content', () => {
    const markup = renderToStaticMarkup(
      <StatCard label="Observations" value={120} format="raw" detail="30 sessions" />,
    );

    expect(markup).toContain('>120<');
    expect(markup).toContain('30 sessions');
  });
});
