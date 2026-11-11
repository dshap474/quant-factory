/**
 * Priority+ overflow for page tab strips: inside a page header, the tabs that do not
 * fit fold, last first, into a trailing "More" menu and return when there is room.
 * The current tab never folds. Strips outside a page header keep sideways scrolling.
 *
 * USAGE:
 *   <TabOverflowProvider><RouteTabs … /></TabOverflowProvider>   // PageHeader does this
 *   const folded = useTabOverflow(stripRef, items.length, activeIndex);
 *   <TabOverflowMore items={folded.map((index) => ({ key, label, to }))} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { ChevronDown } from 'lucide-react';
import {
  createContext,
  type ReactNode,
  type RefObject,
  Suspense,
  useContext,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';

import { ICON_SIZE, ICON_STROKE } from '../lib/icon';
import { lazyNamed } from '../lib/lazy-named';
import type { TabOverflowMenuItem } from './TabOverflowMenu';

// --------------------------------------------------------------------------- #
// Overflow
// --------------------------------------------------------------------------- #

const TabOverflowContext = createContext(false);

/** Turns on folding for every tab strip below it (while `enabled`, default on). */
export function TabOverflowProvider({
  enabled = true,
  children,
}: {
  enabled?: boolean;
  children: ReactNode;
}) {
  return <TabOverflowContext.Provider value={enabled}>{children}</TabOverflowContext.Provider>;
}

/** The More trigger's width before it has rendered once. */
const MORE_FALLBACK_WIDTH = 72;

/**
 * Indexes of the items that do not fit the strip. Items carry `data-tab-index`; the
 * strip must take its width from its host, not from its items, so folding never
 * shrinks the space it measures.
 */
export function useTabOverflow(
  stripRef: RefObject<HTMLElement | null>,
  count: number,
  activeIndex: number,
): number[] {
  const enabled = useContext(TabOverflowContext);
  const [folded, setFolded] = useState<number[]>([]);
  // Folded items render nothing, so each width is the last one seen while visible.
  const widths = useRef<number[]>([]);
  const moreWidth = useRef(MORE_FALLBACK_WIDTH);

  useLayoutEffect(() => {
    const strip = stripRef.current;
    if (!enabled || !strip) return;
    const measure = () => {
      for (const item of strip.querySelectorAll<HTMLElement>('[data-tab-index]')) {
        if (item.offsetWidth > 0) widths.current[Number(item.dataset.tabIndex)] = item.offsetWidth;
      }
      const more = strip.querySelector<HTMLElement>('.ui-tabs-more');
      if (more && more.offsetWidth > 0) moreWidth.current = more.offsetWidth;
      const sizes = Array.from({ length: count }, (_, index) => widths.current[index] ?? 0);
      const next: number[] = [];
      if (sizes.reduce((sum, size) => sum + size, 0) > strip.clientWidth) {
        let room = strip.clientWidth - moreWidth.current - (sizes[activeIndex] ?? 0);
        for (let index = 0; index < count; index += 1) {
          if (index === activeIndex) continue;
          const size = sizes[index] ?? 0;
          // Once one item misses, every later one folds too, so the strip keeps its order.
          if (next.length === 0 && size <= room) room -= size;
          else next.push(index);
        }
      }
      setFolded((previous) => (previous.join() === next.join() ? previous : next));
    };
    measure();
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : undefined;
    observer?.observe(strip);
    return () => observer?.disconnect();
  }, [enabled, stripRef, count, activeIndex]);

  return enabled ? folded : [];
}

// --------------------------------------------------------------------------- #
// More trigger
// --------------------------------------------------------------------------- #

// The menu loads with the first fold, so strips that always fit never pull in Base UI.
const TabOverflowMenu = lazyNamed(() => import('./TabOverflowMenu'), 'TabOverflowMenu');

export function TabOverflowLabel() {
  return (
    <>
      More
      <ChevronDown aria-hidden="true" size={ICON_SIZE} strokeWidth={ICON_STROKE} />
    </>
  );
}

/** The trailing More menu; renders nothing while every tab fits. */
export function TabOverflowMore({ items }: { items: TabOverflowMenuItem[] }) {
  if (items.length === 0) return null;
  return (
    <Suspense
      fallback={
        <span className="ui-tabs-more" aria-hidden="true">
          <TabOverflowLabel />
        </span>
      }
    >
      <TabOverflowMenu items={items} />
    </Suspense>
  );
}
