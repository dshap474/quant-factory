/**
 * Search-first select over a long string roster (e.g. ~500 assets); single or `multiple`.
 *
 * The roster is one virtualized scroll list rather than pages: only the visible rows are
 * mounted, so hundreds or thousands of options scroll smoothly. Typing filters and ranks
 * matches (exact, then prefix, then substring), highlights the matched text, and makes the
 * best match active so Enter picks it. On open the current value is scrolled into view.
 * In `multiple` mode a plain pick selects only that item and closes, like `single`; a
 * Shift/⌘/Ctrl pick (or Shift+Enter) adds or removes it and keeps the panel open. `detail` adds a
 * right-aligned figure per row (e.g. the metric the roster is ranked by). `labelOf` shows a
 * human label in place of an opaque value (e.g. "BTC · Bitcoin" for a UUID key) and search
 * matches the label as well as the value. Long text truncates on one line. The panel is a
 * portaled qf-ui Popover, so clipping or stacking ancestors never hide it. In single mode,
 * ArrowLeft/ArrowRight on the focused, closed trigger step to the previous/next item in
 * roster order (stopping at the ends), so a chart's subject can be paged without opening.
 *
 * USAGE:
 *   <SearchSelect label="asset" items={assets} value={asset} onChange={setAsset} />
 *   <SearchSelect label="file" items={files} value={file} onChange={setFile} placeholder="search coins…" />
 *   <SearchSelect multiple label="assets" items={ranked} value={picked} onChange={setPicked} detail={(a) => pnl[a]} />
 *   <SearchSelect label="asset id" items={ids} value={id} onChange={setId} labelOf={(v) => labels[v]} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useVirtualizer } from '@tanstack/react-virtual';
import { ChevronDown } from 'lucide-react';
import {
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from 'react';
import { ScrollArea } from '../layout/ScrollArea';
import { cn } from '../lib/cn';
import { ICON_SIZE, ICON_STROKE } from '../lib/icon';
import { Popover, PopoverContent, PopoverTrigger } from '../overlay/Popover';
import { Button } from './Button';
import { Input } from './Input';

import './SearchSelect.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

interface SearchSelectBaseProps {
  /** Eyebrow on the trigger and accessible name of the listbox, e.g. "asset". */
  label: string;
  items: readonly string[];
  /** Search placeholder. Default "search…". */
  placeholder?: string;
  /** Right-aligned secondary text for each option row. */
  detail?: (item: string) => ReactNode;
  /** Display text for an item; undefined keeps the raw value. Search matches both. */
  labelOf?: (item: string) => string | undefined;
  className?: string;
}

export type SearchSelectProps = SearchSelectBaseProps &
  (
    | { multiple?: false; value: string | null; onChange: (value: string | null) => void }
    | { multiple: true; value: readonly string[]; onChange: (value: string[]) => void }
  );

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

/** Option row height in px; matches `--control-height-sm` (1.75rem) in SearchSelect.css. */
const ROW_HEIGHT = 28;
/** Rows visible in the list before it scrolls; also the PageUp/PageDown stride. */
const VISIBLE_ROWS = 10;
const OVERSCAN = 8;

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

/** Trigger text for a multi-selection: up to two names, then a "+n" overflow. */
function summarize(values: readonly string[]): string {
  if (values.length === 0) return '—';
  if (values.length <= 2) return values.join(', ');
  return `${values.slice(0, 2).join(', ')} +${values.length - 2}`;
}

/** Best rank of `query` in one text: 0 exact, 1 prefix, 2 substring, null no match. */
function matchRank(text: string, q: string): number | null {
  const at = text.toLowerCase().indexOf(q);
  if (at === -1) return null;
  return text.length === q.length ? 0 : at === 0 ? 1 : 2;
}

/**
 * Exact matches first, then prefix, then substring; roster order within each rank.
 * With `labelOf`, an item matches on its label or its raw value, whichever ranks better.
 */
export function rankMatches(
  items: readonly string[],
  query: string,
  labelOf?: (item: string) => string | undefined,
): readonly string[] {
  const q = query.trim().toLowerCase();
  if (!q) return items;
  return items
    .map((it) => {
      const label = labelOf?.(it);
      const ranks = [matchRank(it, q), label ? matchRank(label, q) : null].filter(
        (rank): rank is number => rank !== null,
      );
      return { it, rank: ranks.length ? Math.min(...ranks) : null };
    })
    .filter((row): row is { it: string; rank: number } => row.rank !== null)
    .sort((a, b) => a.rank - b.rank)
    .map(({ it }) => it);
}

function MatchText({ text, query }: { text: string; query: string }) {
  const q = query.trim().toLowerCase();
  const at = q ? text.toLowerCase().indexOf(q) : -1;
  // One inline span: the option button is a flex row, so bare fragments would gap apart.
  if (at === -1) return <span className="ui-search-select-text">{text}</span>;
  return (
    <span className="ui-search-select-text">
      {text.slice(0, at)}
      <span className="ui-search-select-match">{text.slice(at, at + q.length)}</span>
      {text.slice(at + q.length)}
    </span>
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function SearchSelect(props: SearchSelectProps) {
  const { label, items, placeholder = 'search…', detail, labelOf, className } = props;
  const display = (item: string) => labelOf?.(item) ?? item;
  const selected: readonly string[] = props.multiple
    ? props.value
    : props.value === null
      ? []
      : [props.value];
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(-1);
  const searchRef = useRef<HTMLInputElement | null>(null);
  // State, not a ref: the portaled panel mounts after this render, and the virtualizer
  // must re-render once its scroll element exists.
  const [scrollEl, setScrollEl] = useState<HTMLDivElement | null>(null);
  const attachScroll = useCallback((node: HTMLDivElement | null) => {
    setScrollEl(node);
    return () => setScrollEl(null);
  }, []);
  const openIndexRef = useRef(-1);
  const baseId = useId();
  const listboxId = `${baseId}-listbox`;
  const optionId = (index: number) => `${baseId}-option-${index}`;

  const filtered = useMemo(() => rankMatches(items, query, labelOf), [items, query, labelOf]);
  const activeClamped = activeIndex < filtered.length ? activeIndex : -1;

  const virtualizer = useVirtualizer({
    // Not gated on `open`: the rows must stay mounted while the panel animates out.
    count: filtered.length,
    getScrollElement: () => scrollEl,
    estimateSize: () => ROW_HEIGHT,
    overscan: OVERSCAN,
    initialRect: { width: 0, height: ROW_HEIGHT * VISIBLE_ROWS },
  });

  const close = useCallback(() => setOpen(false), []);

  // Clear the search only once the exit animation has finished, so the closing panel keeps
  // its rows and height instead of collapsing (and re-filtering) while it fades.
  const resetAfterClose = useCallback((isOpen: boolean) => {
    if (isOpen) return;
    setQuery('');
    setActiveIndex(-1);
  }, []);

  const choose = (item: string, toggle = false) => {
    if (props.multiple && toggle) {
      props.onChange(
        selected.includes(item) ? selected.filter((it) => it !== item) : [...selected, item],
      );
      return;
    }
    if (props.multiple) props.onChange([item]);
    else props.onChange(item);
    close();
  };

  const moveTo = (index: number) => {
    setActiveIndex(index);
    virtualizer.scrollToIndex(index, { align: 'auto' });
  };

  // Once the panel's list mounts, bring the current value into view.
  useEffect(() => {
    if (scrollEl && openIndexRef.current >= 0) {
      virtualizer.scrollToIndex(openIndexRef.current, { align: 'center' });
    }
  }, [scrollEl, virtualizer]);

  const openPanel = () => {
    const first = selected[0] === undefined ? -1 : items.indexOf(selected[0]);
    openIndexRef.current = first;
    setActiveIndex(first);
    setOpen(true);
  };

  // Single mode: Left/Right on the closed trigger page through the roster in order.
  const stepValue = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (props.multiple || open || items.length === 0) return;
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    const by = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (by === 0) return;
    event.preventDefault();
    const at = props.value === null ? -1 : items.indexOf(props.value);
    const next = at === -1 ? (by > 0 ? 0 : items.length - 1) : at + by;
    const item = items[next];
    if (item !== undefined && item !== props.value) props.onChange(item);
  };

  const virtualItems = virtualizer.getVirtualItems();
  const countLabel = query.trim()
    ? `${filtered.length.toLocaleString()} of ${items.length.toLocaleString()}`
    : `${items.length.toLocaleString()} ${props.multiple ? label : `${label}s`}`;

  return (
    <Popover
      open={open}
      onOpenChange={(next) => (next ? openPanel() : close())}
      onOpenChangeComplete={resetAfterClose}
    >
      <div className={cn('ui-search-select qf-focus-within', className)}>
        <PopoverTrigger
          render={
            <Button
              variant="control"
              className="ui-search-select-trigger"
              aria-haspopup="listbox"
              aria-expanded={open}
              aria-controls={open ? listboxId : undefined}
              onKeyDown={stepValue}
            />
          }
        >
          <span className="ui-search-select-label">{label}</span>
          <span className="ui-search-select-value">{summarize(selected.map(display))}</span>
          <ChevronDown
            aria-hidden="true"
            className="ui-search-select-chevron"
            size={ICON_SIZE}
            strokeWidth={ICON_STROKE}
          />
        </PopoverTrigger>
      </div>
      <PopoverContent align="start" initialFocus={searchRef} className="ui-search-select-panel">
        <Input
          ref={searchRef}
          className="ui-search-select-search"
          value={query}
          placeholder={placeholder}
          role="combobox"
          aria-label={`Search ${label}`}
          aria-expanded={true}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={activeClamped >= 0 ? optionId(activeClamped) : undefined}
          onChange={(event) => {
            const next = event.target.value;
            setQuery(next);
            // The best-ranked match is active so Enter takes it without arrowing down.
            setActiveIndex(next.trim() ? 0 : -1);
            virtualizer.scrollToOffset(0);
          }}
          onKeyDown={(event) => {
            if (filtered.length === 0) return;
            const last = filtered.length - 1;
            const keys: Record<string, () => number> = {
              ArrowDown: () => (activeClamped >= last ? 0 : activeClamped + 1),
              ArrowUp: () => (activeClamped <= 0 ? last : activeClamped - 1),
              PageDown: () => Math.min(last, Math.max(activeClamped, 0) + VISIBLE_ROWS),
              PageUp: () => Math.max(0, activeClamped - VISIBLE_ROWS),
              Home: () => 0,
              End: () => last,
            };
            const step = keys[event.key];
            if (step) {
              event.preventDefault();
              moveTo(step());
            } else if (event.key === 'Enter' && activeClamped >= 0) {
              event.preventDefault();
              const item = filtered[activeClamped];
              if (item !== undefined) choose(item, event.shiftKey);
            }
          }}
        />
        <ScrollArea
          ref={attachScroll}
          maxHeight={`${ROW_HEIGHT * VISIBLE_ROWS}px`}
          className="ui-search-select-scroll"
        >
          <div
            className="ui-search-select-list"
            id={listboxId}
            role="listbox"
            aria-label={label}
            aria-multiselectable={props.multiple || undefined}
            style={{ height: virtualizer.getTotalSize() }}
          >
            {virtualItems.map((row) => {
              const item = filtered[row.index];
              if (item === undefined) return null;
              const isSelected = selected.includes(item);
              return (
                <Button
                  key={item}
                  variant="nav"
                  role="option"
                  id={optionId(row.index)}
                  className={cn('ui-search-select-option', isSelected && 'is-selected')}
                  style={{ transform: `translateY(${row.start}px)` }}
                  aria-selected={isSelected}
                  aria-setsize={filtered.length}
                  aria-posinset={row.index + 1}
                  tabIndex={-1}
                  data-highlighted={row.index === activeClamped || undefined}
                  onPointerMove={() => {
                    if (row.index !== activeClamped) setActiveIndex(row.index);
                  }}
                  onClick={(event) =>
                    choose(item, event.shiftKey || event.metaKey || event.ctrlKey)
                  }
                >
                  <MatchText text={display(item)} query={query} />
                  {detail ? <span className="ui-search-select-detail">{detail(item)}</span> : null}
                </Button>
              );
            })}
          </div>
        </ScrollArea>
        {filtered.length === 0 ? (
          <p className="ui-search-select-empty">No matches</p>
        ) : (
          <p className="ui-search-select-count">
            {props.multiple ? `${selected.length.toLocaleString()} selected · ` : ''}
            {countLabel}
            {props.multiple ? ' · ⇧-click to add' : ''}
          </p>
        )}
      </PopoverContent>
    </Popover>
  );
}
