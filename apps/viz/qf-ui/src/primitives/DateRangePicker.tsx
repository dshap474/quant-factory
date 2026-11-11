/**
 * UTC calendar-day range picker: a control-shaped trigger that opens a month
 * calendar; click a day or drag across days to pick a range. By keyboard, arrow
 * keys move between days in the rendered grid, the first activation sets a pending
 * start, the second commits the range, and Escape cancels the pending start.
 *
 * USAGE:
 *   <DateRangePicker
 *     from={from}
 *     to={to}
 *     label={from ? `Dates ${from} through ${to}` : 'Filter by date range'}
 *     onChange={(nextFrom, nextTo) => setRange(nextFrom, nextTo)}
 *   />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react';
import { useRef, useState } from 'react';
import { cn } from '../lib/cn';
import { ICON_SIZE, ICON_STROKE } from '../lib/icon';
import { StatusDot } from '../state/Status';
import { Button } from './Button';
import { Text } from './Text';

import './DateRangePicker.css';

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

const UTC_WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface DateRangePickerProps {
  /** UTC calendar day `YYYY-MM-DD`; '' means unbounded. */
  from: string;
  to: string;
  /** Both ends ordered ascending; ('', '') when cleared. */
  onChange: (from: string, to: string) => void;
  /** Accessible name and tooltip of the trigger. */
  label: string;
  /** Accessible name of the calendar group. Default 'Date range calendar'. */
  calendarLabel?: string;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

export function utcDateKey(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function utcMonthStart(date: Date): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
}

export function utcCalendarDays(month: Date): Date[] {
  const first = utcMonthStart(month);
  const start = new Date(first);
  start.setUTCDate(1 - first.getUTCDay());
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(start);
    date.setUTCDate(start.getUTCDate() + index);
    return date;
  });
}

export function orderedDateRange(a: string, b: string): [string, string] {
  return a <= b ? [a, b] : [b, a];
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function DateRangePicker({
  from,
  to,
  onChange,
  label,
  calendarLabel = 'Date range calendar',
  className,
}: DateRangePickerProps) {
  const [calendarMonth, setCalendarMonth] = useState(() => utcMonthStart(new Date()));
  const [dragAnchor, setDragAnchor] = useState('');
  const [dragHover, setDragHover] = useState('');
  const [keyStart, setKeyStart] = useState('');
  const [keyHover, setKeyHover] = useState('');
  const dragAnchorRef = useRef('');
  const dragHoverRef = useRef('');
  const gridRef = useRef<HTMLDivElement | null>(null);

  function clearDrag() {
    dragAnchorRef.current = '';
    dragHoverRef.current = '';
    setDragAnchor('');
    setDragHover('');
  }

  function clearKeyboardStart() {
    setKeyStart('');
    setKeyHover('');
  }

  function selectRange(start: string, end: string) {
    const [orderedFrom, orderedTo] = orderedDateRange(start, end);
    clearDrag();
    clearKeyboardStart();
    onChange(orderedFrom, orderedTo);
  }

  const calendarDays = utcCalendarDays(calendarMonth);

  /** Move focus between day buttons without leaving the rendered month grid. */
  function moveFocus(currentKey: string, delta: number) {
    const buttons = [
      ...(gridRef.current?.querySelectorAll<HTMLButtonElement>('.ui-date-range-day') ?? []),
    ];
    const index = calendarDays.findIndex((date) => utcDateKey(date) === currentKey);
    if (index < 0) return;
    const next = Math.min(buttons.length - 1, Math.max(0, index + delta));
    buttons[next]?.focus();
  }

  const previewRange =
    dragAnchor && dragHover
      ? orderedDateRange(dragAnchor, dragHover)
      : keyStart
        ? orderedDateRange(keyStart, keyHover || keyStart)
        : [from, to];

  return (
    <details className={cn('ui-date-range qf-focus-within', className)}>
      <summary
        className={`ui-button ui-button-control ui-date-range-trigger${from || to ? ' active' : ''}`}
        aria-label={label}
        title={label}
      >
        <CalendarDays aria-hidden="true" size={ICON_SIZE} strokeWidth={ICON_STROKE} />
        {from || to ? <StatusDot tone="running" className="ui-date-range-dot" /> : null}
      </summary>
      <fieldset className="ui-date-range-panel">
        <legend className="sr-only">{calendarLabel}</legend>
        <div className="ui-date-range-header">
          <Button
            type="button"
            variant="plain"
            icon
            aria-label="Previous month"
            onClick={() =>
              setCalendarMonth(
                new Date(
                  Date.UTC(calendarMonth.getUTCFullYear(), calendarMonth.getUTCMonth() - 1, 1),
                ),
              )
            }
          >
            <ChevronLeft aria-hidden="true" size={ICON_SIZE} strokeWidth={ICON_STROKE} />
          </Button>
          <Text variant="data" weight="semibold">
            {calendarMonth.toLocaleDateString(undefined, {
              timeZone: 'UTC',
              month: 'long',
              year: 'numeric',
            })}
          </Text>
          <Button
            type="button"
            variant="plain"
            icon
            aria-label="Next month"
            onClick={() =>
              setCalendarMonth(
                new Date(
                  Date.UTC(calendarMonth.getUTCFullYear(), calendarMonth.getUTCMonth() + 1, 1),
                ),
              )
            }
          >
            <ChevronRight aria-hidden="true" size={ICON_SIZE} strokeWidth={ICON_STROKE} />
          </Button>
        </div>
        <div className="ui-date-range-weekdays" aria-hidden="true">
          {UTC_WEEKDAYS.map((weekday) => (
            <span key={weekday}>{weekday.slice(0, 1)}</span>
          ))}
        </div>
        <div
          className="ui-date-range-grid"
          ref={gridRef}
          onPointerUp={() => {
            if (dragAnchorRef.current) {
              selectRange(dragAnchorRef.current, dragHoverRef.current || dragAnchorRef.current);
            }
          }}
          onPointerCancel={clearDrag}
        >
          {calendarDays.map((date) => {
            const key = utcDateKey(date);
            const inMonth = date.getUTCMonth() === calendarMonth.getUTCMonth();
            const inRange = Boolean(
              previewRange[0] &&
                previewRange[1] &&
                key >= previewRange[0] &&
                key <= previewRange[1],
            );
            const isStart = key === previewRange[0];
            const isEnd = key === previewRange[1];
            const isEdge = isStart || isEnd;
            return (
              <Button
                className={cn(
                  'ui-date-range-day',
                  !inMonth && 'outside',
                  inRange && 'in-range',
                  isEdge && 'range-edge',
                  isStart && 'range-start',
                  isEnd && 'range-end',
                )}
                variant="plain"
                type="button"
                key={key}
                aria-label={date.toLocaleDateString(undefined, {
                  timeZone: 'UTC',
                  weekday: 'long',
                  month: 'long',
                  day: 'numeric',
                  year: 'numeric',
                })}
                aria-pressed={inRange}
                onPointerDown={(event) => {
                  if (event.button !== 0) return;
                  event.preventDefault();
                  dragAnchorRef.current = key;
                  dragHoverRef.current = key;
                  setDragAnchor(key);
                  setDragHover(key);
                }}
                onPointerEnter={() => {
                  if (dragAnchorRef.current) {
                    dragHoverRef.current = key;
                    setDragHover(key);
                  }
                }}
                onFocus={() => {
                  if (keyStart) setKeyHover(key);
                }}
                onKeyDown={(event) => {
                  const delta =
                    event.key === 'ArrowLeft'
                      ? -1
                      : event.key === 'ArrowRight'
                        ? 1
                        : event.key === 'ArrowUp'
                          ? -7
                          : event.key === 'ArrowDown'
                            ? 7
                            : 0;
                  if (delta !== 0) {
                    event.preventDefault();
                    moveFocus(key, delta);
                    return;
                  }
                  if (event.key === 'Escape' && keyStart) {
                    event.preventDefault();
                    clearKeyboardStart();
                  }
                }}
                onClick={(event) => {
                  // `detail === 0` is a keyboard activation; pointer clicks are
                  // handled by the drag path above.
                  if (event.detail !== 0) return;
                  if (keyStart) {
                    selectRange(keyStart, key);
                  } else {
                    setKeyStart(key);
                    setKeyHover(key);
                  }
                }}
              >
                {date.getUTCDate()}
              </Button>
            );
          })}
        </div>
        <div className="ui-date-range-footer">
          <Text variant="data" size="2xs" tone="muted">
            {keyStart
              ? `${keyStart} — press a second day to end the range, Escape to cancel`
              : from
                ? `${from} — ${to}`
                : 'Select or drag across days'}
          </Text>
          <Button
            type="button"
            variant="plain"
            disabled={!from && !to}
            onClick={() => onChange('', '')}
          >
            Clear
          </Button>
        </div>
      </fieldset>
    </details>
  );
}
