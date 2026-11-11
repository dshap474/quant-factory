/**
 * Declarative DataTable cell kinds: formatting, alignment, heat, identifier, status,
 * custom render and accessor-driven sorting.
 *
 * USAGE:
 *   pnpm exec vitest run src/tables/cells/cells.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { MemoryRouter } from '../../../tests/memory-router';
import { DataTable } from '../composed/DataTable';
import { cellText, type DataTableColumn, isNumericKind, resolveColumns } from './cells';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const ROWS = [
  {
    mint: 'So11111111111111111111111111111111111111112',
    trades: 12345,
    ic: 0.04,
    state: 'running',
  },
  { mint: 'Abc', trades: 7, ic: -0.08, state: 'failed' },
  { mint: null, trades: null, ic: null, state: null },
];

function render(node: ReactNode): string {
  return renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>);
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('cell helpers', () => {
  it('treats bare keys as text columns', () => {
    expect(resolveColumns(['a', { key: 'b', kind: 'count' }])).toEqual([
      { key: 'a' },
      { key: 'b', kind: 'count' },
    ]);
  });

  it('marks numeric kinds', () => {
    expect(
      ['number', 'percent', 'money', 'count', 'heat'].every((kind) =>
        isNumericKind(kind as DataTableColumn['kind']),
      ),
    ).toBe(true);
    expect(isNumericKind('identifier')).toBe(false);
    expect(isNumericKind(undefined)).toBe(false);
  });

  it('formats through the shared number formatters with their defaults', () => {
    expect(cellText({ key: 'x', kind: 'number' }, 1.23456, {})).toBe('1.235');
    expect(cellText({ key: 'x', kind: 'percent' }, 0.1234, {})).toBe('12.3%');
    expect(cellText({ key: 'x', kind: 'money', digits: 0 }, 1234, {})).toBe('$1234');
    expect(cellText({ key: 'x', kind: 'count' }, 12345, {})).toBe('12,345');
    expect(cellText({ key: 'x', kind: 'heat', digits: 2 }, 0.041, {})).toBe('0.04');
    expect(cellText({ key: 'x', kind: 'number' }, null, {})).toBe('—');
    expect(cellText({ key: 'x', format: (value) => `v${String(value)}` }, 3, {})).toBe('v3');
  });
});

describe('DataTable cell kinds', () => {
  const columns: DataTableColumn[] = [
    { key: 'mint', header: 'Token', kind: 'identifier', truncate: 'middle' },
    { key: 'trades', header: 'Trades', kind: 'count' },
    {
      key: 'ic',
      header: '5d',
      kind: 'heat',
      heat: { maxAbs: 0.08 },
      title: (v) => `ic ${String(v)}`,
    },
    { key: 'state', header: 'Status', kind: 'status' },
  ];

  it('uses the header label and right-aligns numeric kinds in head and body', () => {
    const markup = render(<DataTable data={ROWS} columns={columns} />);
    expect(markup).toContain('>Token<');
    expect(markup).not.toContain('>mint<');
    expect(markup.match(/<th class="ui-table-head is-numeric text-right/g)).toHaveLength(2);
    expect(markup).toContain('12,345');
  });

  it('renders identifiers, status badges, heat tints and titles', () => {
    const markup = render(<DataTable data={ROWS} columns={columns} />);
    expect(markup).toContain('ui-identifier');
    expect(markup).toContain('ui-status-badge');
    expect(markup).toContain('data-status="failed"');
    expect(markup).toMatch(/style="background:color-mix/);
    expect(markup).toContain('title="ic 0.04"');
  });

  it('shows the kit em dash for missing values in declared columns', () => {
    const markup = render(<DataTable data={ROWS} columns={columns} />);
    expect(markup.split('—').length - 1).toBeGreaterThanOrEqual(4);
  });

  it('renders custom content and sorts through the value accessor', () => {
    const markup = render(
      <DataTable
        data={[
          { name: 'b', score: { v: 1 } },
          { name: 'a', score: { v: 3 } },
        ]}
        columns={[
          { key: 'name', render: (value) => <strong>{String(value)}</strong> },
          { key: 'score', kind: 'number', value: (row) => (row.score as { v: number }).v },
        ]}
        sortable
        defaultSort={{ column: 'score', direction: 'desc' }}
      />,
    );
    expect(markup.indexOf('<strong>a</strong>')).toBeLessThan(markup.indexOf('<strong>b</strong>'));
    expect(markup).toContain('3.000');
  });

  it('right-aligns all-number plain columns in the default density', () => {
    const markup = render(
      <DataTable
        data={[
          { asset: 'BTC', close: 1.5 },
          { asset: 'ETH', close: null },
        ]}
        columns={['asset', 'close']}
      />,
    );
    expect(markup.match(/<th class="ui-table-head is-numeric text-right/g)).toHaveLength(1);
    expect(markup).toContain('data-numeric=""');
    expect(markup).toContain('>1.5000<');
  });

  it('keeps bare-key columns on the plain path', () => {
    const markup = render(
      <DataTable data={[{ asset: 'BTC', close: null }]} columns={['asset', 'close']} />,
    );
    expect(markup).toContain('>asset<');
    expect(markup).toContain('>-<');
  });
});
