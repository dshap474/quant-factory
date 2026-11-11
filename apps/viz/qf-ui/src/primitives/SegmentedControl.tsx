/**
 * Shared single-choice segmented control built from the canonical Button.
 *
 * USAGE:
 *   <SegmentedControl
 *     ariaLabel="Profile view"
 *     options={[{ value: 'session', label: 'Session' }]}
 *     value={view}
 *     onValueChange={setView}
 *   />
 *   <SegmentedControl size="sm" ariaLabel="Filter" options={options} value={v} onValueChange={setV} />
 *   <SegmentedControl variant="tabs" ariaLabel="Page view" options={views} value={view} onValueChange={setView} />
 *
 * `variant="tabs"` is the page-level view switcher: bare text, a ghost pill on hover, and a
 * brand underline that slides to the chosen tab (RouteTabs shares the same indicator).
 * Inside a page header the tabs that do not fit fold into a More menu (tab-overflow.tsx).
 * The default is the one segmented switcher: full-height options on a raised track with an
 * even inset ring, a warm off-white chosen pill that slides between options, and a filled hover.
 * Its options are always equal: each is as wide as the widest label plus its padding. When the
 * host is too narrow for that, the switcher becomes a dropdown, and returns once there is room.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { KeyboardEvent, ReactNode, RefObject } from 'react';
import { Suspense, useLayoutEffect, useRef, useState } from 'react';

import { cn } from '../lib/cn';
import { lazyNamed } from '../lib/lazy-named';
import { Button } from './Button';
import { type ControlSize, controlSizeClass } from './control-size';
import './SegmentedControl.css';
import { TabOverflowMore, useTabOverflow } from './tab-overflow';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface SegmentedControlOption<T extends string> {
  value: T;
  label: ReactNode;
  disabled?: boolean;
}

export interface SegmentedControlProps<T extends string> {
  ariaLabel: string;
  options: Array<SegmentedControlOption<T>>;
  value: T;
  onValueChange: (value: T) => void;
  /** Height step; 'xs' and 'sm' also tighten item padding and type. Default 'md'. */
  size?: ControlSize;
  /** 'segmented' (default) is a light chosen pill on a track; 'tabs' is a page view switcher. */
  variant?: 'segmented' | 'tabs';
  className?: string;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

/** Scroll a horizontally overflowing strip just enough to show `item`; never scrolls ancestors. */
export function revealInStrip(item: HTMLElement | null | undefined): void {
  const strip = item?.parentElement;
  if (!item || !strip || strip.scrollWidth <= strip.clientWidth) return;
  const start = item.offsetLeft;
  const end = start + item.offsetWidth;
  if (start < strip.scrollLeft) strip.scrollLeft = start;
  else if (end > strip.scrollLeft + strip.clientWidth) strip.scrollLeft = end - strip.clientWidth;
}

/** Width of an item's label plus its own padding: the narrowest an equal option may be. */
function itemFloor(item: HTMLElement): number {
  const range = document.createRange();
  range.selectNodeContents(item);
  if (typeof range.getBoundingClientRect !== 'function') return 0;
  const style = getComputedStyle(item);
  return (
    range.getBoundingClientRect().width +
    Number.parseFloat(style.paddingLeft) +
    Number.parseFloat(style.paddingRight)
  );
}

/**
 * Equal options or a dropdown. Sets `--ui-segment-min` (the widest label plus padding) on the
 * strip and returns the width every option needs at that size once its host is narrower,
 * else null. The host must bound the strip (a grid track needs minmax(0, 1fr)).
 * Collapsed, the host keeps that full width as its cap, so its own size says when there is
 * room again.
 */
function useSegmentFit(
  stripRef: RefObject<HTMLElement | null>,
  enabled: boolean,
  labelsKey: string,
): number | null {
  const [fullWidth, setFullWidth] = useState<number | null>(null);
  // biome-ignore lint/correctness/useExhaustiveDependencies: labelsKey re-measures when the labels change; they are read from the DOM.
  useLayoutEffect(() => {
    const strip = stripRef.current;
    if (!enabled || !strip) return;
    const measure = () => {
      // One width decides both ways (collapse below it, return at it), so the two states
      // can never disagree about whether the options fit.
      if (fullWidth !== null) {
        if (strip.clientWidth >= fullWidth) setFullWidth(null);
        return;
      }
      const items = Array.from(strip.querySelectorAll<HTMLElement>('.ui-segmented-control-item'));
      const floor = Math.ceil(Math.max(0, ...items.map(itemFloor)));
      if (floor === 0) return;
      strip.style.setProperty('--ui-segment-min', `${floor}px`);
      const style = getComputedStyle(strip);
      const required = Math.ceil(
        items.length * floor +
          (items.length - 1) * (Number.parseFloat(style.columnGap) || 0) +
          Number.parseFloat(style.paddingLeft) +
          Number.parseFloat(style.paddingRight),
      );
      if (strip.clientWidth + 1 < required) setFullWidth(required);
    };
    measure();
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : undefined;
    observer?.observe(strip);
    return () => observer?.disconnect();
  }, [stripRef, enabled, fullWidth, labelsKey]);
  return enabled ? fullWidth : null;
}

// The dropdown loads the first time a switcher collapses, so roomy pages never pull in Radix.
const SegmentedSelect = lazyNamed(() => import('./Select'), 'SelectControl');

/** Last indicator position per strip label, so a strip that remounts on a view change
 * (pages often render each view in its own frame) still slides from where it was. */
const lastIndicator = new Map<string, { x: number; w: number }>();

/** Slide a strip's `.ui-tabs-indicator` under its chosen item (`aria-checked` or
 * `aria-current`). Re-syncs when `activeKey` changes or the strip resizes. A fresh strip
 * starts at its label's last position (or in place, without motion, on first sight); resizes
 * re-place it without motion. */
export function useTabIndicator(
  stripRef: RefObject<HTMLElement | null>,
  activeKey: unknown,
  enabled = true,
): void {
  // biome-ignore lint/correctness/useExhaustiveDependencies: activeKey re-runs the sync when the chosen item changes; it is read from the DOM, not the closure.
  useLayoutEffect(() => {
    const strip = stripRef.current;
    if (!enabled || !strip) return;
    const key = strip.getAttribute('aria-label') ?? '';
    const place = (x: number, w: number) => {
      strip.style.setProperty('--ui-tab-x', `${x}px`);
      strip.style.setProperty('--ui-tab-w', `${w}px`);
    };
    // `animate` slides from the current placement; a strip never placed, or a layout
    // change (first sizing, fonts, a resized column), jumps into place instead.
    const sync = (animate: boolean) => {
      const item = strip.querySelector<HTMLElement>('[aria-checked="true"], [aria-current="page"]');
      strip.dataset.indicator = item ? 'on' : '';
      if (!item) return;
      const next = { x: item.offsetLeft, w: item.offsetWidth };
      lastIndicator.set(key, next);
      const still = !animate || strip.style.getPropertyValue('--ui-tab-w') === '';
      if (still) delete strip.dataset.indicatorReady;
      place(next.x, next.w);
      if (still) void strip.offsetWidth; // commit the placement before motion turns back on
      strip.dataset.indicatorReady = 'true';
    };
    if (strip.dataset.indicatorReady !== 'true') {
      const previous = lastIndicator.get(key);
      if (previous) {
        place(previous.x, previous.w);
        strip.dataset.indicator = 'on';
        void strip.offsetWidth; // commit the start position so the move below animates
      }
    }
    sync(true);
    let width = strip.offsetWidth;
    const observer =
      typeof ResizeObserver === 'function'
        ? new ResizeObserver(() => {
            // The observer also fires once on observe; only a real size change re-places.
            if (strip.offsetWidth === width) return;
            width = strip.offsetWidth;
            sync(false);
          })
        : undefined;
    observer?.observe(strip);
    return () => observer?.disconnect();
  }, [stripRef, activeKey, enabled]);
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function SegmentedControl<T extends string>({
  ariaLabel,
  options,
  value,
  onValueChange,
  size,
  variant = 'segmented',
  className,
}: SegmentedControlProps<T>) {
  const stripRef = useRef<HTMLDivElement | null>(null);
  const tabs = variant === 'tabs';
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const selectedIndex = options.findIndex((option) => option.value === value);
  const overflow = useTabOverflow(stripRef, options.length, selectedIndex);
  const folded = tabs ? overflow : [];
  const labelsKey = options.map((option) => option.value).join();
  const collapsedWidth = useSegmentFit(stripRef, !tabs, labelsKey);
  useTabIndicator(stripRef, `${value} ${folded.join()} ${collapsedWidth}`);
  const tabbableIndex =
    selectedIndex >= 0 ? selectedIndex : options.findIndex((option) => !option.disabled);

  useLayoutEffect(() => {
    revealInStrip(itemRefs.current[selectedIndex]);
  }, [selectedIndex]);

  const moveFrom = (index: number, delta: number) => {
    for (let step = 1; step <= options.length; step += 1) {
      const next = (((index + delta * step) % options.length) + options.length) % options.length;
      const option = options[next];
      // Folded tabs are reached through the More menu, not the arrow keys.
      if (option && !option.disabled && !folded.includes(next)) {
        onValueChange(option.value);
        itemRefs.current[next]?.focus();
        return;
      }
    }
  };

  const onItemKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      event.preventDefault();
      moveFrom(index, 1);
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      event.preventDefault();
      moveFrom(index, -1);
    } else if (event.key === 'Home') {
      event.preventDefault();
      moveFrom(-1, 1);
    } else if (event.key === 'End') {
      event.preventDefault();
      moveFrom(options.length, -1);
    }
  };

  if (collapsedWidth !== null) {
    const selected = options[selectedIndex];
    return (
      <div
        ref={stripRef}
        className={cn('ui-segmented-control is-collapsed', className)}
        style={{ width: collapsedWidth }}
      >
        <Suspense
          fallback={<span className="ui-segmented-select-fallback">{selected?.label}</span>}
        >
          <SegmentedSelect
            className="ui-segmented-select"
            ariaLabel={ariaLabel}
            {...(size === undefined ? {} : { size })}
            value={value}
            onValueChange={(next) => onValueChange(next as T)}
            options={options}
          />
        </Suspense>
      </div>
    );
  }

  return (
    <div
      ref={stripRef}
      className={cn(
        'ui-segmented-control',
        tabs && 'is-tabs',
        controlSizeClass(size),
        (size === 'sm' || size === 'xs') && 'is-sm',
        className,
      )}
      role="radiogroup"
      aria-label={ariaLabel}
    >
      {options.map((option, index) => (
        <Button
          key={option.value}
          ref={(node) => {
            itemRefs.current[index] = node;
          }}
          className="ui-segmented-control-item"
          data-tab-index={tabs ? index : undefined}
          hidden={folded.includes(index)}
          role="radio"
          aria-checked={value === option.value}
          tabIndex={index === tabbableIndex ? 0 : -1}
          disabled={option.disabled}
          onClick={() => onValueChange(option.value)}
          onKeyDown={(event) => onItemKeyDown(event, index)}
        >
          {option.label}
        </Button>
      ))}
      {tabs ? (
        <TabOverflowMore
          items={options.flatMap((option, index) =>
            folded.includes(index)
              ? [
                  {
                    key: option.value,
                    label: option.label,
                    disabled: option.disabled,
                    onSelect: () => onValueChange(option.value),
                  },
                ]
              : [],
          )}
        />
      ) : null}
      <span className={tabs ? 'ui-tabs-indicator' : 'ui-segmented-pill'} aria-hidden="true" />
    </div>
  );
}
