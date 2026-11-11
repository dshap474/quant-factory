/**
 * Heading/labelling contract for the terminal section frame.
 *
 * USAGE:
 *   pnpm exec vitest run src/frame/TerminalPage.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { MemoryRouter } from '../../tests/memory-router';

import { TerminalPage, TerminalSection } from './TerminalPage';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('TerminalSection', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('labels the section by its heading when an id is given', () => {
    act(() =>
      root.render(
        <TerminalSection id="drawdown-paths" title="paths" right="03 views">
          <p>body</p>
        </TerminalSection>,
      ),
    );

    const section = container.querySelector<HTMLElement>('section.terminal-section');
    expect(section?.getAttribute('aria-labelledby')).toBe('drawdown-paths');
    expect(section?.querySelector('h2')?.id).toBe('drawdown-paths');
    expect(section?.querySelector('.terminal-section-right')?.textContent).toBe('03 views');
  });
});

describe('TerminalPage', () => {
  const markup = (fill: boolean) =>
    renderToStaticMarkup(
      <MemoryRouter>
        <TerminalPage title="Agents" fill={fill}>
          <p>body</p>
        </TerminalPage>
      </MemoryRouter>,
    );

  it('marks the root and the body as fill only when asked', () => {
    expect(markup(true)).toContain('terminal-page is-fill');
    expect(markup(true)).toContain('terminal-page-body is-fill');
    const plain = markup(false);
    expect(plain).toContain('terminal-page-body');
    expect(plain).not.toContain('is-fill');
  });
});
