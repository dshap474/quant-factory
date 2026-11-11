/**
 * Verify the full-panel projection, URL tabs, and honest analysis states.
 * USAGE: pnpm test -- src/lib/components/FeatureFamilyWorkspace.test.tsx
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

import { act, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter, useLocation } from 'react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { FeatureOverview } from '@/lib/api/feature-overview';
import { ViewerRouterProvider } from '@/ui';
import { FeatureFamilyWorkspace } from './FeatureFamilyWorkspace';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const summary = {
  features: 2,
  coverage: 0.75,
  null_cells: 1,
  invalid_cells: 0,
  empty_features: 0,
  constant_features: 0,
};
const base = {
  description: '',
  available: true,
  declared_features: null,
  missing_columns: [],
  definition_changes: [],
  configured_blocks: [],
  blocks: [],
  coverage: [],
  summary,
};
const fixture: FeatureOverview = {
  path: '1d/test/data.parquet',
  category: 'test',
  default_preset: 'default',
  build: {
    id: 'snapshot',
    published_at: null,
    rows: 2,
    assets: 1,
    start: '2024-01-01',
    end: '2024-01-02',
    features: 2,
    keys: ['timestamp', 'asset'],
  },
  presets: [
    { ...base, name: 'default', kind: 'full', columns: ['close', 'ta_rsi'] },
    {
      ...base,
      name: 'v0',
      kind: 'subset',
      columns: ['close'],
      summary: { ...summary, features: 1 },
    },
    {
      ...base,
      name: 'experimental',
      kind: 'configuration',
      columns: [],
      summary: null,
      available: false,
    },
  ],
  analysis: { correlation: 'unverified', ic: 'missing' },
};
vi.mock('@/lib/api/feature-overview', () => ({ useFeatureOverview: () => ({ data: fixture }) }));
vi.mock('./DatasetViewer', () => ({
  DatasetViewer: ({
    selectedColumns,
    mode,
    fill,
    toolbarLead,
  }: {
    selectedColumns: string[];
    mode: string;
    fill?: boolean;
    toolbarLead?: ReactNode;
  }) => (
    <>
      {toolbarLead}
      <div data-testid="viewer" data-columns={selectedColumns.join(',')} data-fill={String(fill)}>
        {mode}
      </div>
    </>
  ),
}));

let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});
function LocationProbe() {
  return <output data-testid="location">{useLocation().search}</output>;
}
function render(search = '') {
  act(() =>
    root.render(
      <MemoryRouter initialEntries={[`/features${search}`]}>
        <ViewerRouterProvider>
          <FeatureFamilyWorkspace path={fixture.path} />
          <LocationProbe />
        </ViewerRouterProvider>
      </MemoryRouter>,
    ),
  );
}
function click(label: string) {
  const target = [...container.querySelectorAll('button')].find(
    (button) => button.getAttribute('aria-label') === label || button.textContent === label,
  );
  if (!target) throw new Error(`Missing button ${label}`);
  act(() => target.click());
}

// --------------------------------------------------------------------------- #
// Behavior
// --------------------------------------------------------------------------- #

it('always shows the full panel, without a preset selector', () => {
  render('?preset=v0');
  expect(container.textContent).not.toContain('Preset');
  expect(container.querySelector('[aria-label="Feature preset"]')).toBeNull();
  expect(container.querySelector('[data-testid="viewer"]')?.textContent).toBe('features');
  click('Data');
  click('Table');
  expect(container.querySelector('[data-testid="viewer"]')?.getAttribute('data-columns')).toBe(
    'close,ta_rsi',
  );
  expect(container.querySelector('[data-testid="viewer"]')?.textContent).toBe('table');
});

it('restores a shared tab URL', () => {
  render('?tab=analysis');
  expect(container.querySelector('[data-testid="viewer"]')?.textContent).toBe('chart');
});

it('does not present unverified analysis as current', () => {
  render('?tab=correlation');
  expect(container.textContent).toContain('Analysis lineage is unverified');
  expect(container.querySelector('[data-testid="viewer"]')).toBeNull();
});

it('bounds the viewer', () => {
  render();
  expect(container.querySelector('[data-testid="viewer"]')?.getAttribute('data-fill')).toBe('true');
});
