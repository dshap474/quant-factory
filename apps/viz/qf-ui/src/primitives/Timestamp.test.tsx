/**
 * Structural tests for the Timestamp primitive.
 *
 * USAGE:
 *   pnpm exec vitest run src/primitives/Timestamp.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { Timestamp } from './Timestamp';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Timestamp', () => {
  it('renders a time element with the ISO instant and the formatted text', () => {
    const html = renderToStaticMarkup(<Timestamp value={Date.UTC(2021, 2, 26, 14, 5)} />);
    expect(html).toBe(
      '<time class="ui-timestamp" dateTime="2021-03-26T14:05:00.000Z" title="2021-03-26T14:05:00.000Z">26 Mar 2021 14:05</time>',
    );
  });

  it('renders an em dash without dateTime for an invalid value', () => {
    const html = renderToStaticMarkup(<Timestamp value="nope" />);
    expect(html).toBe('<time class="ui-timestamp">—</time>');
  });
});
