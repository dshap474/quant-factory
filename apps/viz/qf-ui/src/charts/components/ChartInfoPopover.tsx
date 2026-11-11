/**
 * Accessible chart-title context revealed by pointer hover or keyboard focus.
 *
 * USAGE:
 *   <ChartInfoPopover chartTitle="Price history" sections={[{ label: 'Read', content: '...' }]} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Info } from 'lucide-react';
import { type ReactNode, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import './ChartInfoPopover.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ChartInfoSection {
  label: string;
  content: ReactNode;
}

export interface ChartInfoPopoverProps {
  chartTitle: string;
  sections: readonly ChartInfoSection[];
}

interface PopoverPosition {
  left: number;
  top?: number;
  bottom?: number;
  width: number;
  maxHeight: number;
}

// --------------------------------------------------------------------------- #
// Geometry
// --------------------------------------------------------------------------- #

function popoverPosition(trigger: HTMLButtonElement): PopoverPosition {
  const bounds = trigger.getBoundingClientRect();
  const viewportPadding = 16;
  const gap = 8;
  const width = Math.min(440, window.innerWidth - viewportPadding * 2);
  const left = Math.min(
    Math.max(bounds.left, viewportPadding),
    window.innerWidth - width - viewportPadding,
  );
  const showAbove = bounds.top > window.innerHeight / 2;

  if (showAbove) {
    return {
      left,
      bottom: window.innerHeight - bounds.top + gap,
      width,
      maxHeight: Math.max(bounds.top - gap - viewportPadding, 120),
    };
  }

  return {
    left,
    top: bounds.bottom + gap,
    width,
    maxHeight: Math.max(window.innerHeight - bounds.bottom - gap - viewportPadding, 120),
  };
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ChartInfoPopover({ chartTitle, sections }: ChartInfoPopoverProps) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [position, setPosition] = useState<PopoverPosition | null>(null);
  const tooltipId = useId();
  const open = hovered || focused;

  useLayoutEffect(() => {
    const trigger = triggerRef.current;
    if (!open || !trigger) {
      setPosition(null);
      return undefined;
    }

    setPosition(popoverPosition(trigger));
    const dismiss = () => {
      setHovered(false);
      setFocused(false);
    };
    window.addEventListener('resize', dismiss);
    window.addEventListener('scroll', dismiss, true);
    return () => {
      window.removeEventListener('resize', dismiss);
      window.removeEventListener('scroll', dismiss, true);
    };
  }, [open]);

  return (
    <span className="qf-chart-info">
      <button
        ref={triggerRef}
        type="button"
        className="qf-chart-info-button"
        aria-label={`About ${chartTitle}`}
        aria-describedby={position ? tooltipId : undefined}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onPointerEnter={() => setHovered(true)}
        onPointerLeave={() => setHovered(false)}
        onKeyDown={(event) => {
          if (event.key !== 'Escape') return;
          event.preventDefault();
          setHovered(false);
          setFocused(false);
        }}
      >
        <Info size={11} strokeWidth={1.8} aria-hidden="true" />
      </button>
      {position && typeof document !== 'undefined'
        ? createPortal(
            <div id={tooltipId} className="qf-chart-info-popover" role="tooltip" style={position}>
              <strong className="qf-chart-info-title">About {chartTitle}</strong>
              {sections.map((section) => (
                <section className="qf-chart-info-section" key={section.label}>
                  <strong>{section.label}</strong>
                  <p>{section.content}</p>
                </section>
              ))}
            </div>,
            document.body,
          )
        : null}
    </span>
  );
}
