/**
 * Rendering contracts for the categorical chart key and the chart header note.
 *
 * USAGE:
 *   pnpm test -- chart-key.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { ChartKey } from '../../src/charts/components/ChartKey';
import { ChartNote } from '../../src/charts/components/ChartNote';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('ChartKey', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  it('lists one swatch, name, and optional detail per item and carries the color on the item', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <ChartKey
          ariaLabel="States"
          items={[
            {
              id: 'state-a',
              label: 'State A',
              detail: 'score above zero',
              color: 'var(--color-chart-6)',
            },
            { id: 'quiet', label: 'Quiet', color: 'red' },
          ]}
        />,
      ),
    );

    expect(host.querySelector('ul.qf-chart-key')?.getAttribute('aria-label')).toBe('States');
    const items = [...host.querySelectorAll<HTMLLIElement>('li.qf-chart-key-item')];
    expect(items).toHaveLength(2);
    expect(items[0]?.style.getPropertyValue('--qf-chart-key-color')).toBe('var(--color-chart-6)');
    expect(items[0]?.querySelector('.qf-chart-key-swatch')?.getAttribute('aria-hidden')).toBe(
      'true',
    );
    expect(items[0]?.querySelector('.qf-chart-key-name')?.textContent).toBe('State A');
    expect(items[0]?.querySelector('.qf-chart-key-detail')?.textContent).toBe('score above zero');
    expect(items[1]?.style.getPropertyValue('--qf-chart-key-color')).toBe('red');
    expect(items[1]?.querySelector('.qf-chart-key-detail')).toBeNull();

    await act(async () => root.unmount());
  });

  it('stays static without onEmphasizeChange', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(<ChartKey items={[{ id: 'a', label: 'A', color: 'red' }]} />),
    );

    expect(host.querySelector('ul.qf-chart-key')?.className).toBe('qf-chart-key');
    expect(host.querySelectorAll('button')).toHaveLength(0);

    await act(async () => root.unmount());
  });

  it('renders buttons, reports focus emphasis, and marks emphasized and dimmed rows', async () => {
    const seen: (string | null)[] = [];
    const root = createRoot(host);
    const items = [
      { id: 'a', label: 'A', color: 'red', title: 'Highlight A' },
      { id: 'b', label: 'B', color: 'blue' },
    ];
    await act(async () =>
      root.render(<ChartKey items={items} onEmphasizeChange={(id) => seen.push(id)} />),
    );

    const buttons = [...host.querySelectorAll<HTMLButtonElement>('button.qf-chart-key-button')];
    expect(buttons).toHaveLength(2);
    expect(buttons[0]?.title).toBe('Highlight A');
    expect(buttons[1]?.title).toBe('B');

    await act(async () => {
      buttons[1]?.focus();
    });
    expect(seen).toEqual(['b']);

    await act(async () =>
      root.render(
        <ChartKey items={items} emphasized="b" onEmphasizeChange={(id) => seen.push(id)} />,
      ),
    );
    const rows = [...host.querySelectorAll<HTMLLIElement>('li.qf-chart-key-item')];
    expect(rows[0]?.className).toBe('qf-chart-key-item is-dimmed');
    expect(rows[1]?.className).toBe('qf-chart-key-item is-emphasized');

    await act(async () => root.unmount());
  });
});

describe('ChartNote', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  it('renders a plain note by default and an error tone on request', async () => {
    const root = createRoot(host);
    await act(async () =>
      root.render(
        <>
          <ChartNote>screen only</ChartNote>
          <ChartNote tone="error" className="extra">
            Source unavailable
          </ChartNote>
          <ChartNote tone="waiting">Awaiting local data</ChartNote>
        </>,
      ),
    );

    const notes = [...host.querySelectorAll<HTMLSpanElement>('span.qf-chart-note')];
    expect(notes.map((note) => note.className)).toEqual([
      'qf-chart-note',
      'qf-chart-note is-error extra',
      'qf-chart-note is-waiting',
    ]);
    expect(notes[1]?.textContent).toBe('Source unavailable');

    await act(async () => root.unmount());
  });
});
