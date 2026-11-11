/**
 * Behaviour tests for the shared navigator model hook.
 *
 * USAGE:
 *   pnpm exec vitest run src/ui/shell/useNavigatorModel.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  type NavigatorModel,
  type NavigatorModelOptions,
  useNavigatorModel,
} from './useNavigatorModel';

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

interface Family {
  id: string;
  versions: string[];
}

interface Version {
  id: string;
}

const FAMILIES: Family[] = [
  { id: 'alpha', versions: ['v001', 'v002'] },
  { id: 'beta', versions: ['v010'] },
  { id: 'gamma', versions: [] },
];

const VERSIONS: Record<string, Version[]> = {
  alpha: [{ id: 'v001' }, { id: 'v002' }],
  beta: [{ id: 'v010' }],
  gamma: [],
};

let latest: NavigatorModel<Family, Version> | null = null;

interface ProbeProps extends NavigatorModelOptions<Family, Version> {
  onModel: (model: NavigatorModel<Family, Version>) => void;
}

function Probe({ onModel, ...props }: ProbeProps) {
  const model = useNavigatorModel(props);
  useEffect(() => {
    onModel(model);
  });
  return null;
}

function options(
  overrides: Partial<NavigatorModelOptions<Family, Version>> = {},
): NavigatorModelOptions<Family, Version> {
  return {
    families: FAMILIES,
    familyId: (family) => family.id,
    currentId: 'alpha',
    familyMatches: (family, query) =>
      family.id.includes(query) || family.versions.some((version) => version.includes(query)),
    childMatches: (version, query) => version.id.includes(query),
    childrenQueryKey: (id) => ['test-versions', id],
    loadChildren: async (id) => VERSIONS[id] ?? [],
    ...overrides,
  };
}

function model(): NavigatorModel<Family, Version> {
  if (!latest) throw new Error('model not rendered');
  return latest;
}

async function waitUntil(predicate: () => boolean) {
  await vi.waitFor(() => expect(predicate()).toBe(true));
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('useNavigatorModel', () => {
  let container: HTMLDivElement;
  let root: Root;
  let client: QueryClient;

  beforeEach(() => {
    latest = null;
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    root.unmount();
    container.remove();
    client.clear();
  });

  async function render(props: NavigatorModelOptions<Family, Version>) {
    root.render(
      <QueryClientProvider client={client}>
        <Probe
          {...props}
          onModel={(model) => {
            latest = model;
          }}
        />
      </QueryClientProvider>,
    );
    await vi.waitFor(() => expect(latest).not.toBeNull());
  }

  it('opens the current family by default and loads only its children', async () => {
    const loadChildren = vi.fn(async (id: string) => VERSIONS[id] ?? []);
    await render(options({ loadChildren }));

    expect(model().isExpanded('alpha')).toBe(true);
    expect(model().isExpanded('beta')).toBe(false);
    expect(model().visibleFamilies).toHaveLength(3);
    expect(model().queryNormalized).toBe('');

    await waitUntil(() => model().childrenOf('alpha').children.length === 2);
    expect(model().childrenOf('alpha')).toEqual({
      children: VERSIONS.alpha,
      loading: false,
      error: null,
    });
    expect(loadChildren).toHaveBeenCalledTimes(1);
    expect(loadChildren.mock.calls[0]?.[0]).toBe('alpha');
    expect(model().childrenOf('beta')).toEqual({ children: [], loading: false, error: null });
  });

  it('reports loading while children are pending', async () => {
    await render(options({ loadChildren: () => new Promise(() => {}) }));
    await waitUntil(() => model().childrenOf('alpha').loading);
    expect(model().childrenOf('alpha').children).toEqual([]);
  });

  it('toggles families and loads children on first expansion', async () => {
    await render(options());
    await waitUntil(() => !model().childrenOf('alpha').loading);

    model().toggle('alpha');
    await waitUntil(() => !model().isExpanded('alpha'));

    model().toggle('beta');
    await waitUntil(() => model().isExpanded('beta'));
    await waitUntil(() => model().childrenOf('beta').children.length === 1);
    expect(model().childrenOf('beta').children[0]?.id).toBe('v010');

    model().toggle('beta');
    await waitUntil(() => !model().isExpanded('beta'));
    expect(model().childrenOf('beta').children).toHaveLength(1);
  });

  it('filters families by query, auto-expands visible ones, and filters children', async () => {
    await render(options({ searchExpandLimit: 1 }));
    await waitUntil(() => !model().childrenOf('alpha').loading);

    model().setQuery('  V01');
    await waitUntil(() => model().queryNormalized === 'v01');
    expect(model().visibleFamilies.map((family) => family.id)).toEqual(['beta']);
    expect(model().isExpanded('beta')).toBe(true);
    expect(model().childVisible({ id: 'v010' })).toBe(true);
    expect(model().childVisible({ id: 'v002' })).toBe(false);
    await waitUntil(() => model().childrenOf('beta').children.length === 1);

    model().setQuery('');
    await waitUntil(() => model().queryNormalized === '');
    expect(model().visibleFamilies).toHaveLength(3);
    expect(model().isExpanded('beta')).toBe(false);
    expect(model().childVisible({ id: 'v002' })).toBe(true);
  });

  it('reports load errors per family', async () => {
    await render(
      options({
        currentId: 'beta',
        loadChildren: async () => {
          throw new Error('boom');
        },
      }),
    );
    await waitUntil(() => model().childrenOf('beta').error !== null);
    expect(model().childrenOf('beta')).toEqual({ children: [], loading: false, error: 'boom' });
  });

  it('sorts children with the provided comparator', async () => {
    await render(
      options({
        sortChildren: (left, right) =>
          right.id.localeCompare(left.id, undefined, { numeric: true }),
      }),
    );
    await waitUntil(() => model().childrenOf('alpha').children.length === 2);
    expect(
      model()
        .childrenOf('alpha')
        .children.map((version) => version.id),
    ).toEqual(['v002', 'v001']);
  });

  it('starts with nothing expanded or loaded without a current family', async () => {
    const loadChildren = vi.fn(async (id: string) => VERSIONS[id] ?? []);
    await render(options({ currentId: null, loadChildren }));
    expect(model().isExpanded('alpha')).toBe(false);
    expect(model().childrenOf('alpha')).toEqual({ children: [], loading: false, error: null });
    expect(loadChildren).not.toHaveBeenCalled();
  });
});
