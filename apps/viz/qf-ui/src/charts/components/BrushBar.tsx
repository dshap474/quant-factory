/**
 * Controlled date-domain navigator without Reset controls.
 *
 * USAGE:
 *   <BrushBar data={points} domain={domain} onDomainChange={setDomain} />
 *   <BrushBar data={points} insetLeft={plotLeft} insetRight={plotRight} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { type CSSProperties, useEffect, useMemo, useRef } from 'react';

import './BrushBar.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface BrushPoint {
  date: Date;
  value?: number;
}

export interface BrushBarProps {
  data: readonly BrushPoint[];
  domain?: readonly [Date, Date];
  onDomainChange?: (domain: [Date, Date] | undefined) => void;
  disabled?: boolean;
  /** Pixels from the bar's left edge to the track; pass the plot's left margin to align them. */
  insetLeft?: number;
  /** Pixels from the bar's right edge to the track; pass the plot's right margin. */
  insetRight?: number;
}

interface DragState {
  kind: 'start' | 'end' | 'range';
  pointerX: number;
  start: number;
  end: number;
}

const MIN_SPAN = 0.5;

function insetStyle(
  left: number | undefined,
  right: number | undefined,
): CSSProperties | undefined {
  if (left === undefined && right === undefined) return undefined;
  return {
    ...(left === undefined ? {} : { '--qf-brush-inset-left': `${left}px` }),
    ...(right === undefined ? {} : { '--qf-brush-inset-right': `${right}px` }),
  } as CSSProperties;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function BrushBar({
  data,
  domain,
  onDomainChange,
  disabled = false,
  insetLeft,
  insetRight,
}: BrushBarProps) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const frameRef = useRef<number | null>(null);
  const pendingXRef = useRef<number | null>(null);
  useEffect(
    () => () => {
      if (frameRef.current != null) cancelAnimationFrame(frameRef.current);
    },
    [],
  );
  const fullDomain = useMemo<[Date, Date]>(() => {
    const first = data[0]?.date ?? new Date();
    return [first, data.at(-1)?.date ?? first];
  }, [data]);
  const span = Math.max(fullDomain[1].getTime() - fullDomain[0].getTime(), 1);
  const clamp = (value: number) => Math.min(Math.max(value, 0), 100);
  const toPercent = (date: Date) =>
    clamp(((date.getTime() - fullDomain[0].getTime()) / span) * 100);
  const start = domain ? toPercent(domain[0]) : 0;
  const end = domain ? toPercent(domain[1]) : 100;
  const emit = (nextStart: number, nextEnd: number) => {
    const safeStart = clamp(Math.min(nextStart, nextEnd - MIN_SPAN));
    const safeEnd = clamp(Math.max(nextEnd, safeStart + MIN_SPAN));
    if (safeStart <= 0 && safeEnd >= 100) {
      onDomainChange?.(undefined);
      return;
    }
    onDomainChange?.([
      new Date(fullDomain[0].getTime() + (safeStart / 100) * span),
      new Date(fullDomain[0].getTime() + (safeEnd / 100) * span),
    ]);
  };
  const pointerPercent = (clientX: number) => {
    const bounds = trackRef.current?.getBoundingClientRect();
    return bounds ? ((clientX - bounds.left) / Math.max(bounds.width, 1)) * 100 : 0;
  };
  const applyMove = (clientX: number) => {
    const drag = dragRef.current;
    if (!drag) return;
    const delta = pointerPercent(clientX) - drag.pointerX;
    if (drag.kind === 'start') emit(drag.start + delta, drag.end);
    else if (drag.kind === 'end') emit(drag.start, drag.end + delta);
    else {
      const width = drag.end - drag.start;
      const nextStart = clamp(Math.min(drag.start + delta, 100 - width));
      emit(nextStart, nextStart + width);
    }
  };
  const cancelPendingMove = () => {
    if (frameRef.current != null) cancelAnimationFrame(frameRef.current);
    frameRef.current = null;
    pendingXRef.current = null;
  };
  const begin = (kind: DragState['kind']) => (event: React.PointerEvent<HTMLDivElement>) => {
    if (disabled) return;
    cancelPendingMove();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { kind, pointerX: pointerPercent(event.clientX), start, end };
  };
  // Pointer moves are latched to one emit per animation frame; a pending latch is
  // detected via pendingXRef because sync-rAF environments run the callback before
  // requestAnimationFrame returns its id.
  const move = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return;
    const scheduled = pendingXRef.current != null;
    pendingXRef.current = event.clientX;
    if (scheduled) return;
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      const clientX = pendingXRef.current;
      pendingXRef.current = null;
      if (clientX != null) applyMove(clientX);
    });
  };
  const endDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    // Flush the latest unpainted move so the final position is exact.
    const pendingX = pendingXRef.current;
    cancelPendingMove();
    if (pendingX != null) applyMove(pendingX);
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
  };

  const rangeText = `${start.toFixed(1)}% to ${end.toFixed(1)}% of range`;

  return (
    // biome-ignore lint/a11y/useSemanticElements: preserving the 32px navigator div avoids fieldset browser geometry.
    <div
      className="qf-brush"
      style={insetStyle(insetLeft, insetRight)}
      role="group"
      aria-label="Brush range selector"
      aria-disabled={disabled}
      data-chart-engine="qf-charts"
    >
      <div className="qf-brush-track" ref={trackRef}>
        <div className="qf-brush-selection" style={{ left: `${start}%`, width: `${end - start}%` }}>
          <div
            className="qf-brush-edge qf-brush-edge-start"
            onPointerDown={begin('start')}
            onPointerMove={move}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
          />
          <div
            className="qf-brush-grip"
            onPointerDown={begin('range')}
            onPointerMove={move}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
          />
          <div
            className="qf-brush-edge qf-brush-edge-end"
            onPointerDown={begin('end')}
            onPointerMove={move}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
          />
        </div>
      </div>
      <input
        type="range"
        min={0}
        max={100}
        step={0.5}
        value={start}
        onChange={(event) => emit(Number(event.target.value), end)}
        className="qf-brush-range qf-brush-range-start"
        disabled={disabled}
        aria-label="Brush start"
        aria-valuetext={rangeText}
      />
      <input
        type="range"
        min={0}
        max={100}
        step={0.5}
        value={end}
        onChange={(event) => emit(start, Number(event.target.value))}
        className="qf-brush-range qf-brush-range-end"
        disabled={disabled}
        aria-label="Brush end"
        aria-valuetext={rangeText}
      />
    </div>
  );
}
