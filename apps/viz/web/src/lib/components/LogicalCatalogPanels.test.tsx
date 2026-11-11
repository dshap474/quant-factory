/**
 * Navigator resolution chips: feature sets expose their resolutions (and versions)
 * in the sidebar, data catalogs keep the lake tree's timeframe control.
 *
 * USAGE:
 *   pnpm test -- src/lib/components/LogicalCatalogPanels.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  LogicalCatalogItem,
  LogicalCatalogOption,
  LogicalCatalogResponse,
} from '@/lib/api/catalog';

import {
  CatalogNavigator,
  distinctResolutions,
  optionForResolution,
  versionsAtResolution,
} from './LogicalCatalogPanels';
import { optionKey } from './logical-catalog-model';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

function option(version: string, resolution: string): LogicalCatalogOption {
  return {
    version,
    resolution,
    scope: 'features',
    path: `${resolution}/btc/${version}/data.parquet`,
    updated_at: null,
    exists: true,
  };
}

const OPTIONS = [
  option('latest', '1d'),
  option('v0', '1d'),
  option('v1', '1d'),
  option('latest', '1h'),
];

const ITEM: LogicalCatalogItem = {
  id: 'feature_set:btc',
  kind: 'feature_set',
  layer: 'features',
  label: 'Index BTC',
  category_path: 'btc',
  description: null,
  domain: 'index',
  status: 'active',
  asset_column: false,
  default_resolution: '1d',
  resolutions: OPTIONS,
};

const CATALOG: LogicalCatalogResponse = {
  items: [ITEM],
  total: 1,
  offset: 0,
  limit: 100,
  facets: { layers: ['features'], domains: [], groups: [] },
};

function navigatorProps(overrides: Partial<Parameters<typeof CatalogNavigator>[0]> = {}) {
  return {
    catalog: CATALOG,
    catalogPage: 1,
    catalogPages: 1,
    isData: false,
    isLoading: false,
    layer: 'derived' as const,
    query: '',
    selectedItem: ITEM,
    selectedResolution: '1d',
    options: OPTIONS,
    selectedOption: OPTIONS[0],
    stats: null,
    title: 'Features',
    onUpdate: vi.fn(),
    ...overrides,
  };
}

function click(element: Element | null | undefined) {
  if (!element) throw new Error('missing element');
  act(() => {
    element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  });
}

// --------------------------------------------------------------------------- #
// Pure helpers
// --------------------------------------------------------------------------- #

describe('resolution helpers', () => {
  it('lists distinct resolutions small to large', () => {
    expect(distinctResolutions(OPTIONS)).toEqual(['1h', '1d']);
    expect(distinctResolutions([option('latest', '1d'), option('latest', '1h')])).toEqual([
      '1h',
      '1d',
    ]);
  });

  it('lists the versions available at one resolution', () => {
    expect(versionsAtResolution(OPTIONS, '1d')).toEqual(['latest', 'v0', 'v1']);
    expect(versionsAtResolution(OPTIONS, '1h')).toEqual(['latest']);
  });

  it('keeps the current version when the new resolution carries it', () => {
    expect(optionForResolution(OPTIONS, '1h', OPTIONS[1])).toEqual(option('latest', '1h'));
    expect(optionForResolution(OPTIONS, '1d', option('latest', '1h'))).toEqual(
      option('latest', '1d'),
    );
    expect(optionForResolution(OPTIONS, '5m', OPTIONS[0])).toBeNull();
  });
});

// --------------------------------------------------------------------------- #
// Navigator
// --------------------------------------------------------------------------- #

describe('CatalogNavigator resolution chips', () => {
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

  function render(props: Parameters<typeof CatalogNavigator>[0]) {
    act(() => {
      root.render(
        <MemoryRouter initialEntries={['/features']}>
          <CatalogNavigator {...props} />
        </MemoryRouter>,
      );
    });
  }

  function versionRows() {
    return [...container.querySelectorAll('.ui-navigator-children .ui-navigator-label')].map(
      (label) => label.closest('button'),
    );
  }

  function chips(label: string) {
    return [
      ...container.querySelectorAll(
        `[role="radiogroup"][aria-label="${label}"] .ui-segmented-control-item`,
      ),
    ];
  }

  it('shows resolution chips and nests the versions under the selected set', () => {
    render(navigatorProps());
    expect(chips('Resolution').map((chip) => chip.textContent)).toEqual(['1h', '1d']);
    expect(chips('Resolution').map((chip) => chip.getAttribute('aria-checked'))).toEqual([
      'false',
      'true',
    ]);
    expect(versionRows().map((row) => row?.textContent)).toEqual(['latest', 'v0', 'v1']);
    expect(versionRows().map((row) => row?.getAttribute('aria-current'))).toEqual([
      'true',
      null,
      null,
    ]);
  });

  it('routes chip and version clicks to the option param', () => {
    const onUpdate = vi.fn();
    render(navigatorProps({ onUpdate, selectedOption: OPTIONS[1] }));

    click(chips('Resolution')[0]);
    expect(onUpdate).toHaveBeenLastCalledWith({ option: optionKey(option('latest', '1h')) });

    click(versionRows()[2]);
    expect(onUpdate).toHaveBeenLastCalledWith({ option: optionKey(option('v1', '1d')) });
  });

  it('nests no versions when one version exists at the resolution', () => {
    render(navigatorProps({ selectedOption: option('latest', '1h'), selectedResolution: '1h' }));
    expect(chips('Resolution').map((chip) => chip.getAttribute('aria-checked'))).toEqual([
      'true',
      'false',
    ]);
    expect(versionRows()).toHaveLength(0);
  });

  it('renders no chips without an explicit selection or on the data catalog', () => {
    render(navigatorProps({ selectedItem: null, selectedOption: null, selectedResolution: null }));
    expect(chips('Resolution')).toHaveLength(0);

    render(navigatorProps({ isData: true, layer: 'derived' }));
    expect(chips('Resolution')).toHaveLength(0);
  });
});
