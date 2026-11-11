/**
 * Structural tests for the shared DataTable: scroll region, frame modes, links, sorting.
 *
 * USAGE:
 *   pnpm exec vitest run src/tables/composed/DataTable.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { MemoryRouter } from '../../../tests/memory-router';

import { DataTable } from './DataTable';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const ROWS = [
  { asset: 'ETH', close: 3, link: '/eth' },
  { asset: 'BTC', close: 1, link: '/btc' },
  { asset: 'SOL', close: 2, link: '/sol' },
];
const COLUMNS = ['asset', 'close'];

function render(node: ReactNode): string {
  return renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>);
}

function assetOrder(markup: string): string[] {
  return Array.from(markup.matchAll(/>(ETH|BTC|SOL)</g), (match) => match[1] ?? '');
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('DataTable', () => {
  it('renders a bordered frame around a named both-axis scroll region', () => {
    const markup = render(<DataTable data={ROWS} columns={COLUMNS} />);
    expect(markup).toContain(
      'class="data-table-frame is-framed border border-border rounded-surface"',
    );
    expect(markup).toContain('class="ui-scroll-area is-both data-table-scroll"');
    expect(markup).toContain('role="region"');
    expect(markup).toContain('aria-label="Scrollable data table"');
    expect(markup).toContain('aria-busy="false"');
    expect(markup).not.toContain('<section');
    expect(markup).not.toContain('aria-sort');
    expect(assetOrder(markup)).toEqual(['ETH', 'BTC', 'SOL']);
  });

  it('drops the frame chrome when flush and fills a bounded host when fill', () => {
    const markup = render(<DataTable data={ROWS} columns={COLUMNS} dense flush fill />);
    expect(markup).toContain('class="data-table-frame data-table-dense is-fill"');
    expect(markup).toContain('class="ui-scroll-area is-both is-fill data-table-scroll"');
    expect(markup).not.toContain('border border-border');
  });

  it('keeps mono only on identifier-like columns', () => {
    const markup = render(
      <DataTable
        data={[{ tx_hash: '0xabc', asset_id: 'a7', asset: 'BTC' }]}
        columns={['tx_hash', 'asset_id', 'asset']}
      />,
    );
    const cells = Array.from(markup.matchAll(/<td class="([^"]*)"[^>]*>([^<]*)</g), (m) => [
      m[2],
      m[1],
    ]);
    const classOf = (text: string) => cells.find(([value]) => value === text)?.[1] ?? '';
    expect(classOf('0xabc')).toContain('font-mono');
    expect(classOf('a7')).toContain('font-mono');
    expect(classOf('BTC')).not.toContain('font-mono');
    expect(classOf('BTC')).toContain('tabular-nums');
  });

  it('renders link cells through the shared inline Link', () => {
    const markup = render(<DataTable data={ROWS} columns={COLUMNS} linkColumn="asset" />);
    expect(markup).toContain('ui-link-inline');
    expect(markup).toContain('href="/eth"');
    expect(markup).toContain('>ETH</a>');
  });

  it('orders rows itself when uncontrolled and marks the active header', () => {
    const markup = render(
      <DataTable
        data={ROWS}
        columns={COLUMNS}
        sortable
        defaultSort={{ column: 'close', direction: 'desc' }}
      />,
    );
    expect(assetOrder(markup)).toEqual(['ETH', 'SOL', 'BTC']);
    expect(markup).toContain('aria-sort="descending"');
    expect(markup).toContain('aria-sort="none"');
    expect(markup.match(/ui-sort-button/g)).toHaveLength(2);
  });

  it('limits sort buttons to the listed columns', () => {
    const markup = render(<DataTable data={ROWS} columns={COLUMNS} sortable={['close']} />);
    expect(markup.match(/ui-sort-button/g)).toHaveLength(1);
    expect(markup.match(/aria-sort=/g)).toHaveLength(1);
  });

  it('never reorders data when the host controls the sort', () => {
    const markup = render(
      <DataTable
        data={ROWS}
        columns={COLUMNS}
        sortable
        sort={{ column: 'close', direction: 'asc' }}
        onSortChange={() => undefined}
      />,
    );
    expect(assetOrder(markup)).toEqual(['ETH', 'BTC', 'SOL']);
    expect(markup).toContain('aria-sort="ascending"');
  });
});
