/**
 * Structural tests for the shared Prose primitive.
 *
 * USAGE:
 *   pnpm exec vitest run src/primitives/Prose.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act, createRef } from 'react';
import { createRoot } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { Prose } from './Prose';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('Prose', () => {
  it('renders the prose recipe on a div by default', () => {
    expect(renderToStaticMarkup(<Prose>x</Prose>)).toBe('<div class="prose-dark">x</div>');
  });

  it('adds the reading column, element, and host classes on request', () => {
    expect(
      renderToStaticMarkup(
        <Prose as="article" measure className="extra">
          x
        </Prose>,
      ),
    ).toBe('<article class="prose-dark prose-measure extra">x</article>');
  });

  it('forwards refs to the rendered element', async () => {
    const host = document.createElement('div');
    document.body.appendChild(host);
    const ref = createRef<HTMLElement>();
    const root = createRoot(host);
    await act(async () => root.render(<Prose as="article" ref={ref} />));
    expect(ref.current?.tagName).toBe('ARTICLE');
    await act(async () => root.unmount());
    host.remove();
  });
});
