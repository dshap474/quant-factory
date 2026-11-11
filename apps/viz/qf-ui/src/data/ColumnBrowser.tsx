/**
 * Column browser: pick one item per level of a hierarchy from side-by-side lists
 * (Finder's column view). Each column is a WAI-ARIA single-select listbox whose
 * selection follows focus; every row is a label plus optional right-aligned meta.
 *
 * USAGE:
 *   <ColumnBrowser
 *     ariaLabel="Strategy version"
 *     columns={[
 *       { id: 'family', label: 'Strategy', value: family, onValueChange: setFamily,
 *         options: families.map((name) => ({ value: name })) },
 *       { id: 'version', label: 'Version', value: version, onValueChange: setVersion,
 *         options: [{ value: 'v002', meta: '2024-01-03' }, { value: 'v001', meta: '2024-01-02' }] },
 *     ]}
 *   />
 *   <ColumnBrowser ariaLabel="Pick" rows={6} columns={columns} />
 *   { id: 'preset', label: 'Preset', options: [], value: '', onValueChange, disabled: true }
 *
 * Keyboard: Up/Down select the previous/next row, Home/End the first/last, typing jumps
 * to the next row whose label starts with the typed text, and Left/Right move focus to
 * the neighbouring column. Each column is one tab stop. Columns show `rows` rows (10 by
 * default) and scroll beyond that; the selected row is kept in view inside its column.
 * A `disabled` column keeps its place and width but is greyed out and skipped by focus.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useId,
  useRef,
} from 'react';

import { ScrollArea } from '../layout/ScrollArea';
import { cn } from '../lib/cn';

import './ColumnBrowser.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ColumnBrowserOption {
  value: string;
  /** Row text; defaults to `value`. */
  label?: string;
  /** Right-aligned secondary text, such as a date or count. */
  meta?: ReactNode;
}

export interface ColumnBrowserColumn {
  id: string;
  /** Column heading and the listbox's accessible name. */
  label: string;
  options: ColumnBrowserOption[];
  value: string;
  onValueChange: (value: string) => void;
  /** Shown when the column has no options. */
  emptyLabel?: string;
  /** Greyed out, not focusable and not selectable; the column keeps its place. */
  disabled?: boolean;
}

export interface ColumnBrowserProps {
  ariaLabel: string;
  columns: ColumnBrowserColumn[];
  /** Rows visible before a column scrolls. Default 10. */
  rows?: number;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const TYPEAHEAD_RESET_MS = 500;

/** Scroll `list` just enough to show `row`, centring it when it was out of view. */
export function revealInList(list: HTMLElement, row: HTMLElement): void {
  // Rects, not offsetTop: the list is not the row's offsetParent.
  const top = row.getBoundingClientRect().top - list.getBoundingClientRect().top + list.scrollTop;
  const bottom = top + row.offsetHeight;
  if (top >= list.scrollTop && bottom <= list.scrollTop + list.clientHeight) return;
  list.scrollTop = top - (list.clientHeight - row.offsetHeight) / 2;
}

function optionLabel(option: ColumnBrowserOption): string {
  return option.label ?? option.value;
}

/** Index after `from` (wrapping) whose label starts with `query`, or -1. */
export function typeaheadIndex(
  options: ColumnBrowserOption[],
  query: string,
  from: number,
): number {
  const needle = query.toLowerCase();
  for (let step = 1; step <= options.length; step += 1) {
    const index = (from + step) % options.length;
    const option = options[index];
    if (option && optionLabel(option).toLowerCase().startsWith(needle)) return index;
  }
  return -1;
}

// --------------------------------------------------------------------------- #
// Column
// --------------------------------------------------------------------------- #

function Column({
  column,
  rows,
  onMove,
}: {
  column: ColumnBrowserColumn;
  rows: number;
  onMove: (from: HTMLElement, direction: -1 | 1) => void;
}) {
  const id = useId();
  const list = useRef<HTMLDivElement>(null);
  const typed = useRef({ text: '', at: 0 });
  const { options, value, onValueChange, disabled = false } = column;
  const selected = options.findIndex((option) => option.value === value);
  const optionId = (index: number) => `${id}-option-${index}`;

  useEffect(() => {
    const host = list.current;
    const row = selected >= 0 ? host?.querySelector<HTMLElement>(`[aria-selected="true"]`) : null;
    if (host && row) revealInList(host, row);
  }, [selected]);

  const choose = (index: number) => {
    const option = options[index];
    if (disabled) return;
    if (option && option.value !== value) onValueChange(option.value);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const last = options.length - 1;
    const keys: Record<string, () => void> = {
      ArrowDown: () => choose(Math.min(selected + 1, last)),
      ArrowUp: () => choose(selected < 0 ? 0 : Math.max(selected - 1, 0)),
      Home: () => choose(0),
      End: () => choose(last),
      ArrowLeft: () => onMove(event.currentTarget, -1),
      ArrowRight: () => onMove(event.currentTarget, 1),
    };
    const action = keys[event.key];
    if (action) {
      event.preventDefault();
      action();
      return;
    }
    if (event.key.length !== 1 || event.metaKey || event.ctrlKey || event.altKey) return;
    const now = event.timeStamp;
    const text =
      now - typed.current.at > TYPEAHEAD_RESET_MS ? event.key : typed.current.text + event.key;
    typed.current = { text, at: now };
    // A repeated first letter cycles; a longer prefix refines from the current row.
    const from = text.length > 1 ? Math.max(selected - 1, -1) : selected;
    const match = typeaheadIndex(options, text, from < 0 ? options.length - 1 : from);
    if (match >= 0) {
      event.preventDefault();
      choose(match);
    }
  };

  return (
    <div className={cn('ui-column-browser-column', disabled && 'is-disabled')}>
      <div className="ui-column-browser-heading" id={`${id}-label`}>
        <span>{column.label}</span>
        <span className="ui-column-browser-count">{options.length}</span>
      </div>
      <ScrollArea
        ref={list}
        role="listbox"
        aria-labelledby={`${id}-label`}
        aria-activedescendant={selected >= 0 && !disabled ? optionId(selected) : undefined}
        aria-disabled={disabled || undefined}
        tabIndex={disabled ? -1 : 0}
        data-column-browser-list={disabled ? undefined : ''}
        className="ui-column-browser-list"
        style={{ '--ui-column-browser-rows': rows } as CSSProperties}
        onKeyDown={onKeyDown}
      >
        {options.length === 0 ? (
          <div className="ui-column-browser-empty">{column.emptyLabel ?? 'Nothing to show'}</div>
        ) : (
          options.map((option, index) => (
            // biome-ignore lint/a11y/useFocusableInteractive: focus stays on the listbox (aria-activedescendant)
            // biome-ignore lint/a11y/useKeyWithClickEvents: the listbox owns keyboard selection
            <div
              key={option.value}
              id={optionId(index)}
              role="option"
              aria-selected={index === selected}
              className={cn('ui-column-browser-option', index === selected && 'is-selected')}
              title={optionLabel(option)}
              onClick={() => choose(index)}
            >
              <span className="ui-column-browser-label">{optionLabel(option)}</span>
              {option.meta != null ? (
                <span className="ui-column-browser-meta">{option.meta}</span>
              ) : null}
            </div>
          ))
        )}
      </ScrollArea>
    </div>
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ColumnBrowser({ ariaLabel, columns, rows = 10, className }: ColumnBrowserProps) {
  const root = useRef<HTMLDivElement>(null);
  const move = (from: HTMLElement, direction: -1 | 1) => {
    const lists = [
      ...(root.current?.querySelectorAll<HTMLElement>('[data-column-browser-list]') ?? []),
    ];
    lists[lists.indexOf(from) + direction]?.focus();
  };
  return (
    // biome-ignore lint/a11y/useSemanticElements: a group of listboxes, not a fieldset of form inputs
    <div
      ref={root}
      role="group"
      aria-label={ariaLabel}
      className={cn('ui-column-browser', className)}
      style={{ '--ui-column-browser-columns': columns.length } as CSSProperties}
    >
      {columns.map((column) => (
        <Column key={column.id} column={column} rows={rows} onMove={move} />
      ))}
    </div>
  );
}
