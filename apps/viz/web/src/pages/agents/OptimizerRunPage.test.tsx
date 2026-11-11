/** Run workspace behavior against isolated fixtures, without real store writes.
 * USAGE: pnpm exec vitest run src/pages/agents/OptimizerRunPage.test.tsx
 * @vitest-environment jsdom
 */
// --------------------------------------------------------------------------- #
// Harness
// --------------------------------------------------------------------------- #
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { OptimizerEntry } from '@/lib/api/optimizer';
import { detailFixture, runFixture, stepFixture } from './agents-live-fixture';
import { OptimizerRunPage } from './OptimizerRunPage';

const mock = vi.hoisted(() => ({
  entry: undefined as OptimizerEntry | undefined,
  pending: false,
  error: false,
  fileError: false,
  selection: [] as unknown[],
  folder: '',
}));
vi.mock('@/lib/api/optimizer', async (original) => ({
  ...(await original<object>()),
  useOptimizerRun: () => ({
    data: mock.error ? undefined : mock.entry,
    isFetching: mock.pending,
    isPlaceholderData: false,
    error: mock.error ? new Error('missing') : null,
  }),
  useOptimizerAttempts: () => ({
    data: { attempts: mock.entry ? [mock.entry.detail] : [], total: 1 },
  }),
  useOptimizerFiles: (_id: string, _scope: string, directory: string) => {
    mock.folder = directory;
    return {
      data: {
        entries: [
          { name: 'nested', path: 'nested', directory: true, bytes: null },
          { name: 'sample.parquet', path: 'sample.parquet', directory: false, bytes: 100 },
        ],
      },
    };
  },
  useOptimizerFile: (id: string, scope: string, path: string | null) => {
    mock.selection = [id, scope, path];
    return {
      error: mock.fileError ? new Error('missing') : null,
      data:
        path && !mock.fileError
          ? {
              name: path.split('/').pop(),
              path,
              location: `/repo/version/${path}`,
              bytes: 100,
              markdown: path.endsWith('.md'),
              truncated: false,
              text: path.endsWith('.parquet')
                ? null
                : '# Saved outcome\n<script>window.bad=true</script>\n[Folder](nested/)\n[Code](config.py)\n[Absolute](/repo/version/config.py)',
            }
          : undefined,
    };
  },
}));
vi.mock('@/lib/api/agent-runs', async (original) => ({
  ...(await original<object>()),
  useAgentRunActivity: () => ({ data: { entries: [], truncated: false } }),
}));
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: Root;
function render() {
  act(() =>
    root.render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/agents/strategy-optimizer/runs/selected',
            state: { from: '/agents/strategy-optimizer?view=runs&query=v040&status=failed' },
          },
        ]}
      >
        <Routes>
          <Route path="/agents/strategy-optimizer/runs/:runId" element={<OptimizerRunPage />} />
        </Routes>
      </MemoryRouter>,
    ),
  );
}
function click(label: string) {
  const element = [...container.querySelectorAll('button,a')].find(
    (item) => item.textContent === label,
  );
  expect(element).toBeTruthy();
  act(() => element?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })));
}
beforeEach(() => {
  const run = {
    ...runFixture('selected'),
    target: 'family-a v040',
    status: 'failed' as const,
    active_steps: [],
  };
  const step = { ...stepFixture(run.id, 'audit', null), status: 'failed' as const };
  mock.entry = {
    detail: detailFixture(run, [step]),
    attempt_count: 2,
    research: { status: 'not_tested', documents: ['outcome'] },
    document_paths: { outcome: 'HYPOTHESIS_OUTCOME.selected.md' },
    file_roots: { version: '/repo/version', attempt: '/db/attempt', research: '/db/research' },
  };
  mock.pending = mock.error = mock.fileError = false;
  mock.selection = [];
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});
// --------------------------------------------------------------------------- #
// User navigation and reader contracts
// --------------------------------------------------------------------------- #
it('opens the selected attempt seal and returns to the filtered history', () => {
  render();
  expect(mock.selection).toEqual(['selected', 'version', 'HYPOTHESIS_OUTCOME.selected.md']);
  expect(container.querySelector('a[href*="query=v040"]')?.getAttribute('href')).toBe(
    '/agents/strategy-optimizer?view=runs&query=v040&status=failed',
  );
  expect(container.querySelector('script')).toBeNull();
  expect(container.querySelector('[aria-label="Stage execution"] table')).not.toBeNull();
  expect(container.textContent).toContain('Saved outcome');
  click('Source');
  expect(container.querySelector('pre')?.textContent).toContain('<script>');
  expect(container.querySelector('script')).toBeNull();
});
it('follows markdown folders without appending a markdown extension', () => {
  render();
  click('Folder');
  expect(mock.folder).toBe('nested');
  expect(mock.selection).toEqual(['selected', 'version', null]);
  const parent = container.querySelector('[aria-label="Parent folder"]');
  act(() => parent?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })));
  expect(mock.folder).toBe('');
});
it('follows non-markdown files and presents binary downloads', () => {
  render();
  click('Absolute');
  expect(mock.selection).toEqual(['selected', 'version', 'config.py']);
  click('Outcome');
  click('Code');
  expect(mock.selection).toEqual(['selected', 'version', 'config.py']);
  click('sample.parquet');
  expect(container.textContent).toContain('Binary file');
  expect(container.querySelector('[aria-label="Download file"]')?.getAttribute('href')).toContain(
    'download=true',
  );
});
it('keeps navigation available for missing runs and files', () => {
  mock.error = true;
  render();
  expect(container.textContent).toContain('Run unavailable');
  expect(container.querySelector('a[href*="query=v040"]')).not.toBeNull();
  mock.error = false;
  mock.fileError = true;
  render();
  expect(container.textContent).toContain('File unavailable');
});
it('does not show another run while the selected run loads', () => {
  mock.entry = undefined;
  mock.pending = true;
  render();
  expect(container.textContent).not.toContain('Saved outcome');
  expect(container.querySelector('a[href*="query=v040"]')).not.toBeNull();
});
