/**
 * Structural tests for the routed SectionLayout.
 *
 * USAGE:
 *   pnpm exec vitest run src/ui/frame/SectionLayout.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router';
import { describe, expect, it } from 'vitest';

import { SectionLayout } from './SectionLayout';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function markupAt(path: string, layout: ReactNode): string {
  return renderToStaticMarkup(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/agents" element={layout}>
          <Route index element={<span>index child</span>} />
          <Route path="strategy-optimizer/runs/:runId" element={<span>run child</span>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

const LAYOUT = (
  <SectionLayout
    navigator={<i data-x="nav" />}
    className="agents-shell"
    navigatorHiddenOn="/agents/strategy-optimizer/runs/:runId"
    hiddenClassName="optimizer-run-shell"
  />
);

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('SectionLayout', () => {
  it('renders the navigator and the matched child route', () => {
    const html = markupAt('/agents', LAYOUT);

    expect(html).toContain('data-x="nav"');
    expect(html).toContain('class="section-workspace agents-shell"');
    expect(html).toContain('<div class="section-workspace-content"><span>index child</span></div>');
  });

  it('hides the navigator and swaps the className on the hidden route', () => {
    const html = markupAt('/agents/strategy-optimizer/runs/abc', LAYOUT);

    expect(html).not.toContain('data-x="nav"');
    expect(html).toContain('class="section-workspace optimizer-run-shell"');
    expect(html).toContain('run child');
  });

  it('forwards contentMode to the workspace', () => {
    const html = markupAt(
      '/agents',
      <SectionLayout navigator={<i data-x="nav" />} contentMode="fill">
        <b>explicit</b>
      </SectionLayout>,
    );

    expect(html).toContain('class="section-workspace is-fill-content"');
    expect(html).toContain('class="section-workspace-content is-fill"');
  });

  it('renders explicit children instead of the outlet and keeps the navigator without a pattern', () => {
    const html = markupAt(
      '/agents',
      <SectionLayout navigator={<i data-x="nav" />}>
        <b>explicit</b>
      </SectionLayout>,
    );

    expect(html).toContain('data-x="nav"');
    expect(html).toContain('class="section-workspace"');
    expect(html).toContain('<b>explicit</b>');
    expect(html).not.toContain('index child');
  });

  it('keeps the navigator mounted and remounts only the content pane on in-section navigation', async () => {
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    let go: (path: string) => void = () => undefined;
    function Driver() {
      go = useNavigate();
      return null;
    }
    const node = document.createElement('div');
    document.body.append(node);
    const root = createRoot(node);
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={['/agents/a']}>
          <Driver />
          <Routes>
            <Route path="/agents" element={<SectionLayout navigator={<nav data-x="nav" />} />}>
              <Route path=":id" element={<span>child</span>} />
            </Route>
          </Routes>
        </MemoryRouter>,
      );
    });
    const nav = node.querySelector('[data-x="nav"]');
    const content = node.querySelector('.section-workspace-content');

    await act(async () => {
      go('/agents/b');
    });

    expect(node.querySelector('[data-x="nav"]')).toBe(nav);
    expect(node.querySelector('.section-workspace-content')).not.toBe(content);
    await act(async () => {
      root.unmount();
    });
    node.remove();
  });
});
