// @vitest-environment jsdom
/** Shared comparison formatting and direction tests. USAGE: pnpm vitest run MetricComparisonTable. */

// --------------------------------------------------------------------------- #
// Imports and fixtures
// --------------------------------------------------------------------------- #

import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { type MetricComparisonRow, MetricComparisonTable } from './MetricComparisonTable';

const columns = [
  { id: 'new', label: 'v003' },
  { id: 'old', label: 'v002' },
];
function render(row: MetricComparisonRow) {
  const host = document.createElement('div');
  host.innerHTML = renderToStaticMarkup(
    <MetricComparisonTable
      columns={columns}
      rows={[row]}
      difference={{ current: 'new', reference: 'old' }}
    />,
  );
  return host;
}

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('MetricComparisonTable', () => {
  it('shows signed percentage-point differences and preserves negative values', () => {
    const host = render({
      key: 'return',
      label: 'Total return',
      format: 'percent',
      higherIsBetter: true,
      values: { new: -0.3125, old: -0.125 },
    });
    expect([...host.querySelectorAll('td')].map((cell) => cell.textContent)).toEqual([
      '−31.25%',
      '−12.50%',
      '−18.75 pp',
    ]);
    expect(host.querySelector('td:last-child')?.className).toContain('text-negative');
  });
  it('treats a less negative drawdown as improvement and leaves volatility neutral', () => {
    const row = {
      key: 'risk',
      label: 'Risk',
      format: 'percent' as const,
      values: { new: -0.2, old: -0.3 },
    };
    expect(
      render({ ...row, higherIsBetter: true }).querySelector('td:last-child')?.className,
    ).toContain('text-positive');
    expect(render(row).querySelector('td:last-child')?.className).not.toMatch(
      /text-(positive|negative)/,
    );
  });
  it('does not turn missing or nonnumeric observations into zero differences', () => {
    const host = render({
      key: 'sharpe',
      label: 'Sharpe',
      format: 'number',
      values: { new: null, old: 0.5 },
    });
    expect([...host.querySelectorAll('td')].map((cell) => cell.textContent)).toEqual([
      '—',
      '0.500',
      '—',
    ]);
    expect(host.querySelector('th[scope="row"]')?.textContent).toBe('Sharpe');
  });
  it('wraps text rows in a bounded column and marks numeric rows tabular', () => {
    const text = render({
      key: 'disclosure',
      label: 'Data disclosure',
      format: 'text',
      values: { new: 'Long prose', old: 'More prose' },
    });
    expect(text.querySelector('td')?.className).toBe('ui-table-cell is-wrap');
    expect(text.querySelector('td')?.hasAttribute('data-numeric')).toBe(false);
    const numeric = render({
      key: 'sharpe',
      label: 'Sharpe',
      format: 'number',
      values: { new: 1, old: 0.5 },
    });
    expect(numeric.querySelector('td')?.hasAttribute('data-numeric')).toBe(true);
    expect(numeric.querySelector('td')?.className).not.toContain('is-wrap');
  });
  it('groups adjacent metrics and keeps undefined ratios separate from zero', () => {
    const host = document.createElement('div');
    host.innerHTML = renderToStaticMarkup(
      <MetricComparisonTable
        columns={columns}
        rows={[
          {
            key: 'return',
            label: 'Return',
            group: 'Returns',
            format: 'percent',
            values: { new: 0 },
          },
          {
            key: 'sortino',
            label: 'Sortino',
            group: 'Ratios',
            format: 'number',
            values: { new: null },
          },
          {
            key: 'duration',
            label: 'Time below peak',
            group: 'Drawdowns',
            format: 'days',
            values: { new: 42 },
          },
        ]}
      />,
    );
    expect(
      [...host.querySelectorAll('th[scope="rowgroup"]')].map((cell) => cell.textContent),
    ).toEqual(['Returns', 'Ratios', 'Drawdowns']);
    expect(host.querySelectorAll('tbody')).toHaveLength(3);
    expect(host.textContent).toContain('0.00%');
    expect(host.textContent).toContain('42 d');
    expect(host.querySelectorAll('tbody')[1]?.textContent).toContain('—');
  });
  it('shows rank / N with a relative tint and keeps the values view unchanged', () => {
    const row: MetricComparisonRow = {
      key: 'sortino',
      label: 'Sortino',
      format: 'number',
      values: { new: 1.5, old: 0.4 },
      rank: {
        direction: 'higher',
        cells: {
          new: { rank: 1, count: 25, ties: 0, position: 0, value: 1.234 },
          old: { rank: 12, count: 25, ties: 1, position: null, value: 0.4 },
        },
      },
    };
    const values = render(row);
    expect([...values.querySelectorAll('td')].map((cell) => cell.textContent)).toEqual([
      '1.500',
      '0.400',
      '+1.100',
    ]);
    const host = document.createElement('div');
    host.innerHTML = renderToStaticMarkup(
      <MetricComparisonTable
        view="rank"
        columns={columns}
        rows={[row]}
        difference={{ current: 'new', reference: 'old' }}
      />,
    );
    const cells = [...host.querySelectorAll('td')];
    expect(cells.map((cell) => cell.textContent)).toEqual(['1 / 25', '12 / 25']);
    expect(cells[0]?.getAttribute('style')).toContain('var(--color-tone-success)');
    expect(cells[1]?.getAttribute('style')).toContain('transparent');
    const trigger = host.querySelector('button');
    expect(trigger?.getAttribute('aria-label')).toBe('Sortino, v003: rank 1 / 25');
  });
  it('renders unranked rows and undefined cells as explained neutral dashes', () => {
    const host = document.createElement('div');
    host.innerHTML = renderToStaticMarkup(
      <MetricComparisonTable
        view="rank"
        columns={columns}
        unrankedNote="Not ranked: dollar diagnostic."
        rows={[
          { key: 'fees', label: 'Fees', format: 'money', values: { new: 12, old: 8 } },
          {
            key: 'calmar',
            label: 'Calmar',
            format: 'number',
            values: { new: null, old: 1 },
            rank: {
              direction: 'higher',
              cells: { new: null, old: { rank: 1, count: 1, ties: 0, position: null, value: 1 } },
              missingNote: 'Undefined without drawdown.',
            },
          },
        ]}
      />,
    );
    const cells = [...host.querySelectorAll('td')];
    expect(cells[0]?.textContent).toBe('—Not ranked: dollar diagnostic.');
    expect(cells[0]?.getAttribute('title')).toBe('Not ranked: dollar diagnostic.');
    expect(cells[0]?.getAttribute('style')).toBeNull();
    expect(cells[2]?.getAttribute('title')).toBe('Undefined without drawdown.');
    expect(cells[3]?.textContent).toBe('1 / 1');
  });
});
