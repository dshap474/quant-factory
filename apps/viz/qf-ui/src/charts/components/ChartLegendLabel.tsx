/**
 * Truncated chart-legend label with a viewport-level full-text hover reveal.
 *
 * USAGE:
 *   <ChartLegendLabel>Very long series name</ChartLegendLabel>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { type ReactNode, useCallback, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ChartLegendLabelProps {
  children: ReactNode;
  focusable?: boolean;
}

interface PopoutPosition {
  top: number;
  left?: number;
  right?: number;
  maxWidth: number;
}

function getPopoutPosition(label: HTMLSpanElement): PopoutPosition {
  const bounds = label.getBoundingClientRect();
  const viewportPadding = 16;
  const gap = 8;
  const maxWidth = 352;
  const leftSpace = bounds.left - gap - viewportPadding;
  const rightSpace = window.innerWidth - bounds.right - gap - viewportPadding;
  const top = Math.min(
    Math.max(bounds.top + bounds.height / 2, viewportPadding),
    window.innerHeight - viewportPadding,
  );

  if (rightSpace >= leftSpace) {
    return {
      top,
      left: bounds.right + gap,
      maxWidth: Math.min(maxWidth, Math.max(rightSpace, 0)),
    };
  }

  return {
    top,
    right: window.innerWidth - bounds.left + gap,
    maxWidth: Math.min(maxWidth, Math.max(leftSpace, 0)),
  };
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ChartLegendLabel({ children, focusable = true }: ChartLegendLabelProps) {
  const labelRef = useRef<HTMLSpanElement>(null);
  const [truncated, setTruncated] = useState(false);
  const [popoutPosition, setPopoutPosition] = useState<PopoutPosition | null>(null);
  const tooltipId = useId();

  const measure = useCallback(() => {
    const label = labelRef.current;
    const isTruncated = Boolean(label && label.scrollWidth > label.clientWidth + 1);
    setTruncated(isTruncated);
    if (!isTruncated) setPopoutPosition(null);
  }, []);

  useLayoutEffect(() => {
    measure();
  }, [measure]);

  useLayoutEffect(() => {
    const label = labelRef.current;
    if (!label) return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(label);
    return () => {
      observer.disconnect();
    };
  }, [measure]);

  const showPopout = useCallback(() => {
    const label = labelRef.current;
    if (!label || label.scrollWidth <= label.clientWidth + 1) {
      setTruncated(false);
      setPopoutPosition(null);
      return;
    }
    setTruncated(true);
    setPopoutPosition(getPopoutPosition(label));
  }, []);

  const hidePopout = useCallback(() => {
    setPopoutPosition(null);
  }, []);

  return (
    <span
      className="chart-legend-label-wrap"
      tabIndex={truncated && focusable ? 0 : undefined}
      aria-describedby={popoutPosition ? tooltipId : undefined}
      onFocus={showPopout}
      onBlur={hidePopout}
      onKeyDown={(event) => {
        if (event.key !== 'Escape') return;
        event.preventDefault();
        hidePopout();
      }}
      onPointerEnter={showPopout}
      onPointerLeave={hidePopout}
    >
      <span ref={labelRef} className="chart-legend-label">
        {children}
      </span>
      {popoutPosition && typeof document !== 'undefined'
        ? createPortal(
            <span
              id={tooltipId}
              className="chart-legend-label-popout"
              role="tooltip"
              style={popoutPosition}
            >
              {children}
            </span>,
            document.body,
          )
        : null}
    </span>
  );
}
