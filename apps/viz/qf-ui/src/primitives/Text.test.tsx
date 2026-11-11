/**
 * Structural tests for Text variants and prop overrides.
 *
 * USAGE:
 *   pnpm test -- src/primitives/Text.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { Text } from './Text';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function classesOf(markup: string): string[] {
  const match = markup.match(/class="([^"]*)"/);
  return match ? (match[1] ?? '').split(' ') : [];
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Text', () => {
  it('renders the body recipe by default', () => {
    expect(classesOf(renderToStaticMarkup(<Text>Body</Text>))).toEqual([
      'text-section',
      'font-normal',
      'text-foreground',
    ]);
  });

  it.each([
    {
      variant: 'eyebrow' as const,
      expected: ['text-caption', 'font-medium', 'text-muted-foreground'],
    },
    {
      variant: 'label' as const,
      expected: ['text-caption', 'font-medium', 'text-muted-foreground'],
    },
    {
      variant: 'caption' as const,
      expected: ['text-caption', 'font-normal', 'text-muted-foreground'],
    },
    {
      variant: 'data' as const,
      expected: ['text-caption', 'font-normal', 'text-foreground', 'tabular-nums'],
    },
  ])('renders the $variant recipe', ({ variant, expected }) => {
    expect(classesOf(renderToStaticMarkup(<Text variant={variant}>x</Text>))).toEqual(expected);
  });

  it('renders the accent tone as primary text (no gold)', () => {
    expect(
      classesOf(
        renderToStaticMarkup(
          <Text variant="data" tone="accent">
            x
          </Text>,
        ),
      ),
    ).toEqual(['text-caption', 'font-normal', 'text-foreground', 'tabular-nums']);
  });

  it('lets explicit props override the variant defaults', () => {
    const markup = renderToStaticMarkup(
      <Text variant="caption" size="sm" tone="default" mono>
        x
      </Text>,
    );

    expect(classesOf(markup)).toEqual(['text-body', 'font-normal', 'text-foreground', 'font-mono']);
  });

  it('appends className and honours the element type', () => {
    const markup = renderToStaticMarkup(
      <Text as="p" className="mt-2">
        x
      </Text>,
    );

    expect(markup.startsWith('<p ')).toBe(true);
    expect(classesOf(markup)).toEqual(['text-section', 'font-normal', 'text-foreground', 'mt-2']);
  });
});
