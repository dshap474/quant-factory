/**
 * Client-side paging tests: DataTable `pageSize` and the usePagination /
 * usePagedRows hooks it shares with hosts that page a server offset.
 *
 * USAGE:
 *   pnpm exec vitest run src/tables/composed/DataTable.paging.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, expect, it } from 'vitest';

import { MemoryRouter } from '../../../tests/memory-router';
import { type PagedRows, usePagedRows, usePagination } from '../../data/usePagedRows';
import { DataTable } from './DataTable';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const ROWS = Array.from({ length: 23 }, (_, index) => ({ id: `row-${index + 1}`, n: index + 1 }));

function mount(ui: ReactNode): { node: HTMLDivElement; unmount: () => void } {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const node = document.createElement('div');
  const root = createRoot(node);
  act(() => root.render(<MemoryRouter>{ui}</MemoryRouter>));
  return { node, unmount: () => act(() => root.unmount()) };
}

function bodyIds(node: HTMLElement): string[] {
  return Array.from(
    node.querySelectorAll('tbody tr td:first-child'),
    (cell) => cell.textContent ?? '',
  );
}

function clickButton(node: HTMLElement, label: string) {
  const button = Array.from(node.querySelectorAll('button')).find(
    (item) => item.textContent?.trim() === label || item.getAttribute('aria-label') === label,
  );
  if (!button) throw new Error(`missing ${label}`);
  act(() => button.click());
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('DataTable pageSize', () => {
  it('renders one page with a range label and pages forward', () => {
    const { node, unmount } = mount(<DataTable data={ROWS} columns={['id', 'n']} pageSize={10} />);
    expect(bodyIds(node)).toHaveLength(10);
    expect(bodyIds(node)[0]).toBe('row-1');
    expect(node.querySelector('.ui-pagination-label')?.textContent).toBe('1–10 of 23 · 1/3');

    clickButton(node, 'Next');
    expect(bodyIds(node)[0]).toBe('row-11');
    clickButton(node, 'Next');
    expect(bodyIds(node)).toHaveLength(3);
    expect(node.querySelector('.ui-pagination-label')?.textContent).toBe('21–23 of 23 · 3/3');
    expect(node.textContent).not.toContain('Showing');
    unmount();
  });

  it('hides the pagination for a single page and while loading', () => {
    const single = mount(<DataTable data={ROWS.slice(0, 10)} columns={['id']} pageSize={10} />);
    expect(single.node.querySelector('nav[aria-label="Pagination"]')).toBeNull();
    single.unmount();

    const loading = mount(<DataTable data={ROWS} columns={['id']} pageSize={10} loading />);
    expect(loading.node.querySelector('nav[aria-label="Pagination"]')).toBeNull();
    expect(loading.node.querySelectorAll('tbody tr')).toHaveLength(10);
    loading.unmount();
  });
});

describe('usePagedRows and usePagination', () => {
  it('clamps the page when the rows shrink', () => {
    const latest: { current: PagedRows<number> | null } = { current: null };
    function Probe({ rows }: { rows: number[] }) {
      latest.current = usePagedRows(rows, 5);
      return null;
    }
    const values = Array.from({ length: 12 }, (_, index) => index);
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    const node = document.createElement('div');
    const root = createRoot(node);
    act(() => root.render(<Probe rows={values} />));
    act(() => latest.current?.setPage(3));
    expect(latest.current?.rows).toEqual([10, 11]);
    act(() => root.render(<Probe rows={values.slice(0, 7)} />));
    expect(latest.current?.page).toBe(2);
    expect(latest.current?.rows).toEqual([5, 6]);
    act(() => root.unmount());
  });

  it('keeps the requested page while a server total is unknown', () => {
    const latest: { current: ReturnType<typeof usePagination> | null } = { current: null };
    function Probe({ count }: { count: number | undefined }) {
      latest.current = usePagination({ count, pageSize: 10 });
      return null;
    }
    const node = document.createElement('div');
    const root = createRoot(node);
    act(() => root.render(<Probe count={45} />));
    act(() => latest.current?.setPage(4));
    act(() => root.render(<Probe count={undefined} />));
    expect(latest.current?.start).toBe(30);
    act(() => root.render(<Probe count={45} />));
    expect(latest.current?.page).toBe(4);
    expect(latest.current?.pageCount).toBe(5);
    act(() => root.unmount());
  });
});
