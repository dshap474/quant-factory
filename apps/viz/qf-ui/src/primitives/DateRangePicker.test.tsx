/**
 * Trigger, dot, footer, clear, and keyboard range/arrow-navigation contracts for
 * DateRangePicker.
 *
 * USAGE:
 *   pnpm exec vitest run src/primitives/DateRangePicker.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DateRangePicker } from './DateRangePicker';

/** The calendar opens on the current UTC month, so range fixtures must live in it. */
function dayInCurrentMonth(day: number): string {
  const now = new Date();
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('DateRangePicker', () => {
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

  it('labels the trigger and shows no marker while the range is empty', () => {
    act(() => {
      root.render(<DateRangePicker from="" to="" onChange={() => undefined} label="Pick dates" />);
    });

    const trigger = container.querySelector('summary');
    expect(trigger?.getAttribute('aria-label')).toBe('Pick dates');
    expect(trigger?.getAttribute('title')).toBe('Pick dates');
    expect(trigger?.className).not.toContain('active');
    expect(container.querySelector('.ui-date-range-dot')).toBeNull();
  });

  it('wears the shared focus-within recipe on the wrapper so one ring frames the composite', () => {
    act(() => {
      root.render(<DateRangePicker from="" to="" onChange={() => undefined} label="Pick dates" />);
    });

    expect(container.querySelector('.ui-date-range')?.classList.contains('qf-focus-within')).toBe(
      true,
    );
  });

  it('marks the trigger and reports the range in the footer when one is set', () => {
    act(() => {
      root.render(
        <DateRangePicker
          from="2024-01-02"
          to="2024-01-09"
          onChange={() => undefined}
          label="Pick dates"
        />,
      );
    });

    expect(container.querySelector('summary')?.className).toContain('active');
    expect(container.querySelector('.ui-date-range-dot')).not.toBeNull();
    expect(container.querySelector('.ui-date-range-footer')?.textContent).toContain(
      '2024-01-02 — 2024-01-09',
    );
  });

  it('marks the run ends so the band and the edge chips meet without a notch', () => {
    act(() => {
      root.render(
        <DateRangePicker
          from={dayInCurrentMonth(10)}
          to={dayInCurrentMonth(17)}
          onChange={() => undefined}
          label="Pick dates"
        />,
      );
    });

    const dayFor = (label: string) =>
      [...container.querySelectorAll<HTMLButtonElement>('.ui-date-range-day:not(.outside)')].find(
        (day) => day.textContent === label,
      );

    const start = dayFor('10');
    const end = dayFor('17');
    const middle = dayFor('13');
    expect(start?.className).toContain('range-edge');
    expect(start?.className).toContain('range-start');
    expect(start?.className).not.toContain('range-end');
    expect(end?.className).toContain('range-edge');
    expect(end?.className).toContain('range-end');
    expect(end?.className).not.toContain('range-start');
    expect(middle?.className).toContain('in-range');
    expect(middle?.className).not.toContain('range-edge');
  });

  it('gives a single-day selection both run ends so it stays fully rounded', () => {
    act(() => {
      root.render(
        <DateRangePicker
          from={dayInCurrentMonth(10)}
          to={dayInCurrentMonth(10)}
          onChange={() => undefined}
          label="Pick dates"
        />,
      );
    });

    const day = [
      ...container.querySelectorAll<HTMLButtonElement>('.ui-date-range-day:not(.outside)'),
    ].find((candidate) => candidate.textContent === '10');
    expect(day?.className).toContain('range-start');
    expect(day?.className).toContain('range-end');
  });

  it('picks a two-step range by keyboard and cancels the pending start on Escape', () => {
    const onChange = vi.fn();
    act(() => {
      root.render(<DateRangePicker from="" to="" onChange={onChange} label="Pick dates" />);
    });

    const days = () => [...container.querySelectorAll<HTMLButtonElement>('.ui-date-range-day')];
    const footer = () => container.querySelector('.ui-date-range-footer')?.textContent ?? '';

    // First keyboard activation only arms a pending start.
    act(() => days()[7]?.click());
    expect(onChange).not.toHaveBeenCalled();
    expect(footer()).toContain('press a second day to end the range');
    expect(days()[7]?.className).toContain('range-start');

    // Escape cancels it.
    act(() => {
      days()[7]?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    expect(footer()).toContain('Select or drag across days');

    // Re-arm, then a second activation commits the ordered range.
    act(() => days()[7]?.click());
    act(() => days()[9]?.click());
    expect(onChange).toHaveBeenCalledTimes(1);
    const [selectedFrom, selectedTo] = onChange.mock.calls[0] as [string, string];
    expect(selectedFrom).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(selectedTo).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(selectedFrom < selectedTo).toBe(true);
  });

  it('moves focus between days with the arrow keys without changing month', () => {
    act(() => {
      root.render(<DateRangePicker from="" to="" onChange={() => undefined} label="Pick dates" />);
    });

    const days = [...container.querySelectorAll<HTMLButtonElement>('.ui-date-range-day')];
    const month = container.querySelector('.ui-date-range-header')?.textContent;
    act(() => days[10]?.focus());

    act(() => {
      days[10]?.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    });
    expect(document.activeElement).toBe(days[11]);

    act(() => {
      days[11]?.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    });
    expect(document.activeElement).toBe(days[18]);

    expect(container.querySelector('.ui-date-range-header')?.textContent).toBe(month);
  });

  it('disables Clear when empty and clears a set range', () => {
    const onChange = vi.fn();
    act(() => {
      root.render(<DateRangePicker from="" to="" onChange={onChange} label="Pick dates" />);
    });

    const clearOf = () =>
      [...container.querySelectorAll<HTMLButtonElement>('.ui-date-range-footer button')].find(
        (button) => button.textContent === 'Clear',
      );
    expect(clearOf()?.disabled).toBe(true);

    act(() => {
      root.render(
        <DateRangePicker
          from="2024-01-02"
          to="2024-01-09"
          onChange={onChange}
          label="Pick dates"
        />,
      );
    });
    expect(clearOf()?.disabled).toBe(false);
    act(() => clearOf()?.click());
    expect(onChange).toHaveBeenCalledWith('', '');
  });
});
