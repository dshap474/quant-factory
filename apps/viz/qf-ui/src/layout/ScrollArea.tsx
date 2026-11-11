/**
 * Bounded scroll region: the one way a container owns its overflow.
 *
 * USAGE:
 *   <ScrollArea>{longList}</ScrollArea>                                   // vertical, sized by its host
 *   <ScrollArea axis="both" fill label="Scrollable data table">…</ScrollArea>
 *   <ScrollArea axis="x">{wideStrip}</ScrollArea>
 *   <ScrollArea axis="both" maxHeight="32rem" label="Cross-section">{table}</ScrollArea>
 *
 * `fill` flex-fills a bounded flex-column host (flex: 1; min-height: 0) instead of sizing to
 * content. The host must bound its own height or the region never scrolls.
 *
 * The region publishes its overflow state as `data-edge-start` / `data-edge-end` /
 * `data-edge-top` / `data-edge-bottom` (each the axis letter when more content lies that
 * way, otherwise empty), plus `data-overflow-x` / `data-overflow-y`, which scope wheel
 * containment to an axis that really scrolls so a fitting region never blocks page scroll.
 * A region holding a table never contains the vertical wheel: at its top or bottom the next
 * scroll moves the page. ScrollArea.css keys the edge fade off those attributes; macOS
 * overlay scrollbars are invisible at rest, so nothing else hints at clipped content. A
 * pinned table header (`TableHeader sticky`) is measured into `--ui-scroll-inset-top` so the
 * top fade starts below it instead of erasing it.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { type ComponentPropsWithRef, useCallback } from 'react';

import { cn } from '../lib/cn';

import './ScrollArea.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type ScrollAxis = 'x' | 'y' | 'both';

export interface ScrollAreaProps extends ComponentPropsWithRef<'div'> {
  /** Scrollable axis. Defaults to vertical. */
  axis?: ScrollAxis;
  /** Flex-fill a bounded flex-column host instead of sizing to content. */
  fill?: boolean;
  /** Accessible name; when given the element is announced as a landmark region. */
  label?: string;
  /** Upper bound on the region's height; content beyond it scrolls. */
  maxHeight?: string;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

/** Scroll position is state, so the edge affordance cannot be pure CSS: publish it. Each
 * side also gets its remaining scroll distance, so its fade narrows to nothing as the
 * content runs out instead of switching off at the edge. */
function writeEdges(node: HTMLDivElement): void {
  const room = {
    start: node.scrollLeft,
    end: node.scrollWidth - node.clientWidth - node.scrollLeft,
    top: node.scrollTop,
    bottom: node.scrollHeight - node.clientHeight - node.scrollTop,
  };
  node.dataset.overflowX = String(node.scrollWidth - node.clientWidth > 1);
  node.dataset.overflowY = String(node.scrollHeight - node.clientHeight > 1);
  node.dataset.edgeStart = room.start > 1 ? 'x' : '';
  node.dataset.edgeEnd = room.end > 1 ? 'x' : '';
  node.dataset.edgeTop = room.top > 1 ? 'y' : '';
  node.dataset.edgeBottom = room.bottom > 1 ? 'y' : '';
  for (const [side, px] of Object.entries(room)) {
    node.style.setProperty(`--ui-scroll-room-${side}`, `${Math.max(0, px)}px`);
  }
  // A pinned table header stays opaque; the top fade starts at its bottom edge. Only a header
  // pinned to this region counts: one inside a nested scroll region pins there, and counting
  // it would cut an opaque band across the top of this one.
  const head = [...node.querySelectorAll<HTMLElement>('.ui-table-sticky-head')].find(
    (item) => item.closest('.ui-scroll-area') === node,
  );
  node.style.setProperty('--ui-scroll-inset-top', `${head?.offsetHeight ?? 0}px`);
}

/** Attach the overflow tracker, returning the React 19 ref cleanup. */
export function trackScrollEdges(node: HTMLDivElement): () => void {
  const sync = () => writeEdges(node);
  sync();
  node.addEventListener('scroll', sync, { passive: true });
  const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(sync) : undefined;
  observer?.observe(node);
  return () => {
    node.removeEventListener('scroll', sync);
    observer?.disconnect();
  };
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ScrollArea({
  axis = 'y',
  fill = false,
  label,
  maxHeight,
  className,
  style,
  ref,
  ...props
}: ScrollAreaProps) {
  const classes = cn('ui-scroll-area', `is-${axis}`, fill && 'is-fill', className);
  const resolvedStyle = maxHeight ? { maxHeight, ...style } : style;

  // Compose with the caller's ref; a host (DataTable) may already own one.
  const attach = useCallback(
    (node: HTMLDivElement | null) => {
      let detachCaller: (() => void) | undefined;
      if (typeof ref === 'function') {
        const returned = ref(node);
        if (typeof returned === 'function') detachCaller = returned;
      } else if (ref) {
        ref.current = node;
      }
      const detachEdges = node ? trackScrollEdges(node) : undefined;
      return () => {
        detachEdges?.();
        if (detachCaller) detachCaller();
        else if (typeof ref !== 'function' && ref) ref.current = null;
      };
    },
    [ref],
  );

  if (label) {
    return (
      // biome-ignore lint/a11y/useSemanticElements: a scroll region is a div; hosts (DataTable) assert no <section> chrome
      <div
        className={classes}
        role="region"
        aria-label={label}
        style={resolvedStyle}
        ref={attach}
        {...props}
      />
    );
  }
  return <div className={classes} style={resolvedStyle} ref={attach} {...props} />;
}
