/**
 * Overflow-only popout for navigator rows: when a row's label or detail is cut by
 * the navigator width, hovering or keyboard-focusing the row shows the full text
 * in a small card beside the navigator. Rows that fit never show one.
 *
 * The first popout opens after a short intent delay; moving to a neighbouring row
 * while one is visible swaps it instantly (the skip-delay pattern used by
 * Radix/Primer tooltips). The card is a visual aid only: the row already carries
 * the full text in the DOM, so the card is aria-hidden and never takes pointer events.
 *
 * USAGE:
 *   const { listProps, popout } = useNavigatorOverflowPopout(side);
 *   <nav {...listProps}>…rows…</nav>
 *   {popout}
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  type FocusEvent,
  type PointerEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';

import './NavigatorOverflowPopout.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

interface PopoutContent {
  label: string;
  details: string[];
  tag: { label: string; tone: string } | null;
  meta: string | null;
  /** Viewport anchor: the row's vertical center and the navigator's docking edge. */
  anchorY: number;
  anchorX: number;
  side: 'start' | 'end';
}

export interface NavigatorOverflowPopout {
  listProps: {
    onPointerOver: (event: PointerEvent<HTMLElement>) => void;
    onPointerLeave: () => void;
    onFocus: (event: FocusEvent<HTMLElement>) => void;
    onBlur: () => void;
  };
  popout: ReactNode;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const OPEN_DELAY_MS = 350;
const SKIP_DELAY_MS = 300;
const EDGE_GAP_PX = 6;

function isClipped(element: Element | null): boolean {
  return element instanceof HTMLElement && element.scrollWidth > element.clientWidth + 1;
}

/** True when any text inside the row is cut off by the row width. */
export function rowOverflows(row: HTMLElement): boolean {
  if (isClipped(row.querySelector('.ui-navigator-label'))) return true;
  const copy = row.querySelector('.ui-navigator-copy');
  if (isClipped(copy)) return true;
  return Array.from(row.querySelectorAll('.ui-navigator-detail > *')).some(isClipped);
}

function readContent(row: HTMLElement, side: 'start' | 'end'): PopoutContent {
  const aside = row.closest('aside');
  const rowRect = row.getBoundingClientRect();
  const edgeRect = (aside ?? row).getBoundingClientRect();
  const detail = row.querySelector('.ui-navigator-detail');
  const detailLines = detail
    ? Array.from(detail.children).map((child) => child.textContent?.trim() ?? '')
    : [];
  const tag = row.querySelector<HTMLElement>('.ui-navigator-tag');
  const meta = row.querySelector('.ui-navigator-meta');
  return {
    label: row.querySelector('.ui-navigator-label')?.textContent?.trim() ?? '',
    details: detailLines.length
      ? detailLines.filter(Boolean)
      : [detail?.textContent?.trim() ?? ''].filter(Boolean),
    tag: tag ? { label: tag.textContent?.trim() ?? '', tone: tag.dataset.tone ?? 'neutral' } : null,
    meta: meta?.textContent?.trim() || null,
    anchorY: Math.min(Math.max(rowRect.top + rowRect.height / 2, 24), window.innerHeight - 24),
    anchorX: side === 'end' ? edgeRect.left - EDGE_GAP_PX : edgeRect.right + EDGE_GAP_PX,
    side,
  };
}

// --------------------------------------------------------------------------- #
// Hook
// --------------------------------------------------------------------------- #

export function useNavigatorOverflowPopout(
  side: 'start' | 'end' = 'start',
): NavigatorOverflowPopout {
  const [content, setContent] = useState<PopoutContent | null>(null);
  const rowRef = useRef<HTMLElement | null>(null);
  const openTimer = useRef<number | undefined>(undefined);
  const lastClosedAt = useRef(0);
  const visible = useRef(false);

  const close = useCallback(() => {
    window.clearTimeout(openTimer.current);
    rowRef.current = null;
    if (visible.current) lastClosedAt.current = Date.now();
    visible.current = false;
    setContent(null);
  }, []);

  const show = useCallback(
    (row: HTMLElement) => {
      visible.current = true;
      setContent(readContent(row, side));
    },
    [side],
  );

  const target = useCallback(
    (row: HTMLElement | null) => {
      if (row === rowRef.current) return;
      window.clearTimeout(openTimer.current);
      rowRef.current = row;
      if (!row || !rowOverflows(row)) {
        if (visible.current) close();
        return;
      }
      const warm = visible.current || Date.now() - lastClosedAt.current < SKIP_DELAY_MS;
      if (warm) {
        show(row);
      } else {
        openTimer.current = window.setTimeout(() => {
          if (rowRef.current === row) show(row);
        }, OPEN_DELAY_MS);
      }
    },
    [close, show],
  );

  useEffect(() => {
    if (!content) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
    };
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
      window.removeEventListener('keydown', onKey);
    };
  }, [content, close]);

  useEffect(() => () => window.clearTimeout(openTimer.current), []);

  const rowOf = (element: EventTarget | null) =>
    element instanceof Element ? element.closest<HTMLElement>('.ui-navigator-row') : null;

  const listProps: NavigatorOverflowPopout['listProps'] = {
    onPointerOver: (event) => {
      if (event.pointerType === 'touch') return;
      target(rowOf(event.target));
    },
    onPointerLeave: close,
    onFocus: (event) => {
      const row = rowOf(event.target);
      if (row?.matches(':focus-visible')) target(row);
    },
    onBlur: close,
  };

  const popout =
    content && typeof document !== 'undefined'
      ? createPortal(
          <div
            className="ui-navigator-popout"
            data-side={content.side}
            aria-hidden="true"
            style={{ top: content.anchorY, left: content.anchorX }}
          >
            <span className="ui-navigator-popout-label">{content.label}</span>
            {content.details.map((line, index) => (
              <span key={index} className="ui-navigator-popout-detail">
                {line}
              </span>
            ))}
            {content.tag || content.meta ? (
              <span className="ui-navigator-popout-facts">
                {content.tag ? (
                  <span className="ui-navigator-tag" data-tone={content.tag.tone}>
                    {content.tag.label}
                  </span>
                ) : null}
                {content.meta ? <span className="ui-navigator-meta">{content.meta}</span> : null}
              </span>
            ) : null}
          </div>,
          document.body,
        )
      : null;

  return { listProps, popout };
}
