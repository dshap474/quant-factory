/** Dashboard schema, stale-state, clock, roster, pinned runs, peek and usage-label tests.
 * USAGE: pnpm exec vitest run src/pages/agents/AgentsLiveDashboard.test.tsx
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports and harness
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { agentRunsSchema } from '@/lib/api/agent-runs';
import { AgentsPage } from '../AgentsPage';
import { AgentsLiveDashboard } from './AgentsLiveDashboard';
import { detailFixture, runFixture, snapshotFixture } from './agents-live-fixture';
import { RunExpansion } from './RunExpansion';
import { runState } from './runs';

const query = vi.hoisted(() => ({
  data: undefined as unknown,
  isError: false,
  isPending: false,
  isFetching: false,
  dataUpdatedAt: 0,
  refetch: vi.fn(),
}));
const detail = vi.hoisted(() => ({ data: undefined as unknown, isPending: false }));
vi.mock('@/lib/api/agent-runs', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useAgentRuns: () => query,
  useAgentRunStats: () => ({ data: undefined, refetch: vi.fn() }),
  useAgentRunDetail: () => detail,
  useAgentRunActivity: () => ({ data: undefined, isPending: false }),
  useAgentStepReport: () => ({ data: undefined, isPending: false }),
}));
vi.mock('@/lib/api/agents', () => ({
  useAgents: () => ({ data: { agents: [] }, isLoading: false }),
}));
vi.mock('@/ui/frame/PipelineArchitectureMap', () => ({
  PipelineArchitectureMap: () => <div>Catalog inventory</div>,
}));
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: Root;
function render(element = <AgentsLiveDashboard />) {
  act(() => root.render(<MemoryRouter>{element}</MemoryRouter>));
}
function click(element: Element | null | undefined) {
  act(() => void element?.dispatchEvent(new MouseEvent('click', { bubbles: true })));
}
function text(selector: string) {
  return container.querySelector(selector)?.textContent ?? '';
}
beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-01-01T00:00:05Z'));
  query.data = snapshotFixture();
  query.isError = false;
  query.isPending = false;
  query.dataUpdatedAt = Date.now();
  detail.data = undefined;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.useRealTimers();
});

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

it('validates schema boundary and rejects invalid execution states or dates', () => {
  expect(agentRunsSchema.safeParse(snapshotFixture()).success).toBe(true);
  const invalid = snapshotFixture();
  expect(agentRunsSchema.safeParse({ ...invalid, fetched_at: 'yesterday' }).success).toBe(false);
  expect(
    agentRunsSchema.safeParse({ ...invalid, runs: [{ ...runFixture(), status: 'healthy' }] })
      .success,
  ).toBe(false);
  expect(
    agentRunsSchema.safeParse({ ...invalid, runs: [{ ...runFixture(), last_step: undefined }] })
      .success,
  ).toBe(false);
});

it('ticks active elapsed time but freezes on stale data and keeps the running count', () => {
  render();
  expect(text('[aria-label="Run summary"]')).toContain('Running1');
  act(() => vi.advanceTimersByTime(2000));
  expect(text('[aria-label="Agent runs"] tbody')).toContain('7s');
  query.isError = true;
  render();
  expect(container.textContent).toContain('Disconnected · stale data');
  expect(text('[aria-label="Run summary"]')).toContain('Running1');
  expect(text('[aria-label="Agent runs"] tbody')).toContain('5s');
  expect(vi.getTimerCount()).toBe(0);
});

it('shows an error without counts, stable loading, and an honest empty roster', () => {
  query.data = undefined;
  query.isError = true;
  render();
  expect(container.textContent).toContain('Unable to load agents.');
  expect(container.querySelector('[aria-label="Run summary"]')).toBeNull();
  query.isError = false;
  query.isFetching = true;
  render();
  expect(container.querySelector('[aria-label="Loading agent runs"]')).not.toBeNull();
  query.isFetching = false;
  query.data = snapshotFixture([]);
  render();
  expect(container.textContent).toContain('No runs recorded yet.');
  expect(text('[aria-label="Agent roster"]')).toContain('Idle');
  expect(text('[aria-label="Agent roster"]')).toContain('Not monitored');
  expect(vi.getTimerCount()).toBe(0);
});

it('reports an unavailable store instead of an idle-looking dashboard', () => {
  const snapshot = snapshotFixture([]);
  snapshot.store = { available: false, schema_version: null, detail: 'No run database yet.' };
  query.data = snapshot;
  render();
  expect(container.textContent).toContain('Run store unavailable · No run database yet.');
  expect(text('[aria-label="Agent roster"]')).toContain('Unknown');
});

it('pins running rows above history and links each run to its page', () => {
  const finished = {
    ...runFixture('fixture-002'),
    status: 'succeeded' as const,
    active_steps: [],
    label: 'finished run',
  };
  query.data = snapshotFixture([finished, runFixture()]);
  render();
  const rows = container.querySelectorAll('[aria-label="Agent runs"] tbody tr');
  expect(rows[0].textContent).toContain('fixture-family v001');
  expect(rows[1].textContent).toContain('finished run');
  expect(rows[0].querySelector('a')?.getAttribute('href')).toBe('/agents/runs/fixture-001');
  expect(text('[aria-label="Agent roster"]')).toContain('1 running');
});

it('surfaces health that contradicts the status in the table and the roster', () => {
  const run = runFixture();
  expect(runState(run)).toBe('running');
  run.health = 'unresponsive';
  run.health_detail = 'No heartbeat for 90s';
  query.data = snapshotFixture([run]);
  render();
  expect(runState(run)).toBe('unresponsive');
  expect(text('[aria-label="Agent runs"] tbody tr')).toContain('Unresponsive');
  const roster = container.querySelector('[aria-label="Agent roster"] .ui-status-badge');
  expect([roster?.textContent, roster?.className.includes('text-tone-critical')]).toEqual([
    'Unresponsive',
    true,
  ]);
});

it('peeks at a run with its stages, error and an Open run link', () => {
  const run = { ...runFixture(), status: 'failed' as const, error: 'author timed out' };
  query.data = snapshotFixture([run]);
  render();
  const runs = '[aria-label="Agent runs"] tbody';
  const toggle = container.querySelector(`${runs} button[aria-expanded]`);
  expect(toggle?.getAttribute('aria-expanded')).toBe('false');
  click(toggle);
  const peek = container.querySelectorAll(`${runs} tr`)[1];
  expect(peek?.textContent).toContain('author · 1');
  expect(peek?.textContent).toContain('author timed out');
  expect(
    [...(peek?.querySelectorAll('a') ?? [])]
      .find((link) => link.textContent === 'Open run →')
      ?.getAttribute('href'),
  ).toBe('/agents/runs/fixture-001');
  click(container.querySelector(`${runs} button[aria-expanded]`));
  expect(container.querySelectorAll(`${runs} tr`)).toHaveLength(1);
});

it('retains Catalog and exposes accessible keyboard view selection', () => {
  render(<AgentsPage />);
  const radio = container.querySelector('[role="radio"]');
  expect(radio?.getAttribute('aria-checked')).toBe('true');
  act(() =>
    radio?.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })),
  );
  expect(container.textContent).toContain('Catalog inventory');
  expect(container.querySelector('[aria-label="Run summary"]')).toBeNull();
});

it.each([
  ['claude', '123 uncached input tokens'],
  ['codex', '123 input tokens (including cache reads)'],
  ['test-engine', '123 provider-reported input tokens'],
])('labels %s usage without conflating cached input or inventing cost', (engine, label) => {
  const run = runFixture();
  const value = detailFixture(run);
  value.steps[0] = {
    ...value.steps[0],
    engine,
    artifacts: {
      directory: null,
      report_available: false,
      usage: {
        input_tokens: 123,
        output_tokens: 7,
        cache_read_tokens: 100,
        cache_write_tokens: 89,
        thinking_tokens: null,
        total_tokens: null,
        wall_seconds: 5,
        cost_usd: null,
        cost_basis: null,
      },
    },
  };
  detail.data = value;
  render(<RunExpansion run={run} />);
  const usage = text('[aria-label="Step evidence"]');
  expect(usage).toContain(label);
  expect(usage).toContain('100 cache-read input');
  expect(usage).toContain('89 cache-write input');
  expect(usage).not.toContain('$');
});

it('renders the expansion feed for a live run', () => {
  const run = runFixture();
  detail.data = detailFixture(run);
  render(<RunExpansion run={run} />);
  expect(text('[aria-label="Run detail"]')).toContain('candidate-1');
});
