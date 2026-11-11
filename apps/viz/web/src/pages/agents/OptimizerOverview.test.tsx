/** Agent pages: shared overview and runs, the optimizer's history extension, prompts and docs.
 * USAGE: pnpm exec vitest run src/pages/agents/OptimizerOverview.test.tsx
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Isolated query data and React harness
// --------------------------------------------------------------------------- #
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { AgentRun } from '@/lib/api/agent-runs';
import type { OptimizerEntry } from '@/lib/api/optimizer';
import { AgentDetailPage } from './AgentDetailPage';
import { detailFixture, runFixture, snapshotFixture, stepFixture } from './agents-live-fixture';

const mock = vi.hoisted(() => ({
  history: [] as unknown[],
  runs: [] as unknown[],
  error: false,
  filters: [] as Record<string, unknown>[],
}));
vi.mock('@/lib/api/agent-runs', async (original) => ({
  ...(await original<object>()),
  useAgentRuns: () => ({
    data: snapshotFixture(mock.runs as AgentRun[]),
    isPending: false,
    isError: false,
    dataUpdatedAt: 0,
    refetch: vi.fn(),
  }),
  useAgentRunStats: () => ({ data: undefined }),
}));
vi.mock('@/lib/api/optimizer', () => ({
  useOptimizerHistory: (filters: Record<string, unknown>) => {
    mock.filters.push(filters);
    return {
      isPending: false,
      isError: mock.error,
      data: { entries: mock.history, total: mock.history.length, limit: filters.limit },
    };
  },
  useOptimizerAttempts: () => ({
    isPending: false,
    data: { attempts: (mock.history as OptimizerEntry[]).map((e) => e.detail), total: 1 },
  }),
}));
vi.mock('@/lib/api/agents', () => ({
  useAgents: () => ({
    data: {
      agents: [
        {
          id: 'strategy-optimizer',
          bindings: [
            { stage: 'author', engine: 'codex', model: 'configured-author', effort: 'high' },
          ],
        },
      ],
    },
  }),
  useAgentPrompts: () => ({
    data: {
      name: 'Strategy Optimizer',
      prompts: ['author', 'audit', 'seal'].map((name, i) => ({
        id: `stage-${i + 1}`,
        name,
        stage: i + 1,
        kind: 'resident-stage',
        path: `${name}.md`,
        markdown: `# ${name} instructions`,
      })),
    },
  }),
  useAgentReadme: () => ({
    data: { name: 'Agent', path: 'README.md', markdown: '# Agent documentation' },
  }),
}));
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: Root;
function render(agent = 'strategy-optimizer') {
  act(() =>
    root.render(
      <MemoryRouter initialEntries={[`/agents/${agent}`]}>
        <Routes>
          <Route path="/agents/:agentId" element={<AgentDetailPage />} />
        </Routes>
      </MemoryRouter>,
    ),
  );
}
function button(text: string) {
  return [...container.querySelectorAll('button')].find((b) => b.textContent === text);
}
function click(element: Element | undefined | null) {
  expect(element).toBeTruthy();
  act(() => element?.dispatchEvent(new MouseEvent('click', { bubbles: true })));
}
function entry(): OptimizerEntry {
  const run = {
    ...runFixture('completed'),
    status: 'succeeded' as const,
    active_steps: [],
    target: 'family-a v040',
  };
  const step = { ...stepFixture(run.id, 'seal', 'v040'), status: 'succeeded' as const };
  return {
    detail: detailFixture(run, [step]),
    attempt_count: 2,
    research: { status: 'falsified', documents: ['spec', 'review', 'outcome'] },
  };
}
beforeEach(() => {
  mock.history = [entry()];
  mock.runs = [runFixture()];
  mock.error = false;
  mock.filters = [];
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

// --------------------------------------------------------------------------- #
// User-visible contracts
// --------------------------------------------------------------------------- #
it('defaults to the shared overview with bindings, stages and linked runs', () => {
  render();
  expect(button('Overview')?.getAttribute('aria-checked')).toBe('true');
  expect(container.textContent).toContain('author · codex · configured-author · high');
  expect(container.querySelector('[aria-pressed] strong')?.textContent).toBe('author');
  const run = [...container.querySelectorAll('a')].find((link) =>
    link.textContent?.includes('fixture-family v001'),
  );
  expect(run?.getAttribute('href')).toBe('/agents/runs/fixture-001');
  expect(mock.filters).toHaveLength(0);
});
it('opens prompts and retains documentation', () => {
  render();
  click(button('Prompts'));
  expect(container.textContent).toContain('author instructions');
  click(button('Documentation'));
  expect(container.textContent).toContain('Agent documentation');
});
it('adds the server-filtered history with research outcomes under Runs', () => {
  render();
  click(button('Runs'));
  expect(container.querySelector('[aria-label="strategy-optimizer runs"]')).not.toBeNull();
  expect(container.querySelector('[aria-label="Search target or version"]')).not.toBeNull();
  expect(mock.filters.at(-1)).toMatchObject({ mode: 'all', limit: 20, offset: 0 });
  const links = [...container.querySelectorAll('a')];
  expect(
    links.find((link) => link.textContent?.includes('family-a v040'))?.getAttribute('href'),
  ).toBe('/agents/strategy-optimizer/runs/completed');
  expect(links.find((link) => link.textContent === 'Falsified')?.getAttribute('href')).toBe(
    '/agents/strategy-optimizer/runs/completed',
  );
  expect(container.textContent).toContain('2 attempts');
});
it('shows unavailable history honestly', () => {
  mock.error = true;
  render();
  click(button('Runs'));
  expect(container.textContent).toContain('History unavailable');
});
it('gives other agents the shared views without the optimizer history', () => {
  render('example');
  expect(button('Overview')?.getAttribute('aria-checked')).toBe('true');
  click(button('Runs'));
  expect(button('Runs')?.getAttribute('aria-checked')).toBe('true');
  expect(container.querySelector('[aria-label="Search target or version"]')).toBeNull();
  expect(mock.filters).toHaveLength(0);
});
