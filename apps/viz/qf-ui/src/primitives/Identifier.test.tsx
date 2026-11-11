/**
 * Structural tests for the Identifier primitive.
 *
 * USAGE:
 *   pnpm exec vitest run src/primitives/Identifier.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { Identifier } from './Identifier';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

const RUN_ID = '20260101T120000000000Z-v001-00000001';

describe('Identifier', () => {
  it('end mode renders the full value with a title and the ellipsis modifier', () => {
    const html = renderToStaticMarkup(<Identifier value={RUN_ID} />);
    expect(html).toBe(
      `<span class="ui-identifier is-truncate-end" title="${RUN_ID}">${RUN_ID}</span>`,
    );
  });

  it('middle mode shows head and tail and keeps the full value for screen readers', () => {
    const html = renderToStaticMarkup(<Identifier value={RUN_ID} truncate="middle" />);
    expect(html).toContain('<span aria-hidden="true">20260101…000001</span>');
    expect(html).toContain(`<span class="sr-only">${RUN_ID}</span>`);
    expect(html).toContain(`title="${RUN_ID}"`);
  });

  it('renders a short value unchanged in middle mode', () => {
    const html = renderToStaticMarkup(<Identifier value="abcdef0123" truncate="middle" />);
    expect(html).toBe('<span class="ui-identifier" title="abcdef0123">abcdef0123</span>');
  });

  it('none mode renders the full value without the ellipsis modifier', () => {
    const html = renderToStaticMarkup(<Identifier value={RUN_ID} truncate="none" className="x" />);
    expect(html).toBe(`<span class="ui-identifier x" title="${RUN_ID}">${RUN_ID}</span>`);
  });
});
