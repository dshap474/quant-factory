/**
 * Virtualization tests for DataTable: a window of rows in the DOM, exact spacer extents,
 * absolute row indices, and the opt-out paths.
 *
 * USAGE:
 *   pnpm exec vitest run src/tables/composed/DataTable.virtualize.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from '../../../tests/memory-router';

import { DataTable, VIRTUALIZE_MIN_ROWS } from './DataTable';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const ROW_HEIGHT = 20;
const VIEWPORT = 200;
const TOTAL = 1000;
const ROWS = Array.from({ length: TOTAL }, (_, index) => ({ id: index, value: index * 2 }));
const COLUMNS = ['id', 'value'];

/** jsdom has no layout: give every element a fixed viewport so the virtualizer sees a window. */
function stubLayout(): void {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    x: 0,
    y: 0,
    top: 0,
    left: 0,
    right: 400,
    bottom: VIEWPORT,
    width: 400,
    height: VIEWPORT,
    toJSON: () => ({}),
  });
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(VIEWPORT);
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockReturnValue(400);
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('DataTable virtualization', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    stubLayout();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.restoreAllMocks();
  });

  function mount(node: ReactNode): void {
    act(() => root.render(<MemoryRouter>{node}</MemoryRouter>));
  }

  function dataRows(): HTMLTableRowElement[] {
    return Array.from(
      container.querySelectorAll<HTMLTableRowElement>('tbody tr:not(.data-table-spacer)'),
    );
  }

  function spacerHeights(): number[] {
    return Array.from(
      container.querySelectorAll<HTMLElement>('tbody tr.data-table-spacer td'),
      (cell) => Number.parseFloat(cell.style.height),
    );
  }

  it('renders only a window of the rows, with a spacer standing in for the rest', () => {
    mount(
      <DataTable
        data={ROWS}
        columns={COLUMNS}
        maxRows={TOTAL}
        virtualize={{ rowHeight: ROW_HEIGHT, overscan: 2 }}
      />,
    );
    const rows = dataRows();
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.length).toBeLessThan(40);
    expect(rows[0]?.textContent).toContain('0');

    // Window + spacers cover the full scroll extent exactly.
    const rendered = rows.length * ROW_HEIGHT;
    const spacers = spacerHeights().reduce((sum, height) => sum + height, 0);
    expect(rendered + spacers).toBe(TOTAL * ROW_HEIGHT);
    expect(rows[0]?.style.height).toBe(`${ROW_HEIGHT}px`);
  });

  it('labels the virtual table with its full row count and absolute row indices', () => {
    mount(<DataTable data={ROWS} columns={COLUMNS} maxRows={TOTAL} virtualize />);
    expect(container.querySelector('table')?.getAttribute('aria-rowcount')).toBe(`${TOTAL + 1}`);
    expect(dataRows()[0]?.getAttribute('aria-rowindex')).toBe('2');
  });

  it('keeps the gutter numbering absolute across the window', () => {
    mount(
      <DataTable data={ROWS} columns={COLUMNS} maxRows={TOTAL} dense rowOffset={0} virtualize />,
    );
    expect(dataRows()[0]?.querySelector('.data-table-gutter')?.textContent).toBe('1');
  });

  it('marks odd rows for the zebra by absolute index', () => {
    mount(<DataTable data={ROWS} columns={COLUMNS} maxRows={TOTAL} virtualize />);
    const [first, second] = dataRows();
    expect(first?.hasAttribute('data-zebra')).toBe(false);
    expect(second?.hasAttribute('data-zebra')).toBe(true);
  });

  it('renders every row when virtualize is off', () => {
    mount(<DataTable data={ROWS} columns={COLUMNS} maxRows={TOTAL} />);
    expect(dataRows()).toHaveLength(TOTAL);
    expect(container.querySelector('.data-table-spacer')).toBeNull();
    expect(container.querySelector('table')?.hasAttribute('aria-rowcount')).toBe(false);
  });

  it('renders every row at or below the virtualization threshold', () => {
    mount(
      <DataTable
        data={ROWS.slice(0, VIRTUALIZE_MIN_ROWS)}
        columns={COLUMNS}
        maxRows={TOTAL}
        virtualize
      />,
    );
    expect(dataRows()).toHaveLength(VIRTUALIZE_MIN_ROWS);
    expect(container.querySelector('.data-table-spacer')).toBeNull();
  });

  it('sorts before windowing', () => {
    mount(
      <DataTable
        data={ROWS}
        columns={COLUMNS}
        maxRows={TOTAL}
        virtualize
        sortable
        defaultSort={{ column: 'id', direction: 'desc' }}
      />,
    );
    expect(dataRows()[0]?.textContent).toContain(`${TOTAL - 1}`);
  });

  it('does not window while loading', () => {
    mount(<DataTable data={ROWS} columns={COLUMNS} maxRows={TOTAL} virtualize loading />);
    expect(container.querySelector('.data-table-spacer')).toBeNull();
    expect(container.querySelectorAll('.data-table-skeleton-bar').length).toBeGreaterThan(0);
  });
});
