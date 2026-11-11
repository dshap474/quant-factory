/**
 * Accessible 24px legend collapse control.
 *
 * `inline` renders a ghost panel toggle that sits in a header row; otherwise the button
 * floats at `position` over its positioned parent.
 *
 * USAGE:
 *   <LegendCollapseButton collapsed={false} onToggle={toggle} />
 *   <LegendCollapseButton inline collapsed={collapsed} onToggle={toggle} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  PanelRightClose,
  PanelRightOpen,
} from 'lucide-react';
import type { CSSProperties } from 'react';

import './LegendCollapseButton.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface LegendCollapseButtonProps {
  collapsed: boolean;
  onToggle: () => void;
  position?: 'right' | 'left' | 'top' | 'bottom';
  /** Render in document flow as a header toggle instead of floating over the legend. */
  inline?: boolean;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function LegendCollapseButton({
  collapsed,
  onToggle,
  position = 'right',
  inline = false,
  className = '',
}: LegendCollapseButtonProps) {
  const label = collapsed ? 'Expand legend' : 'Collapse legend';
  if (inline) {
    return (
      <button
        type="button"
        onClick={onToggle}
        className={`legend-collapse-button is-inline ${className}`.trim()}
        style={{ width: '24px', height: '24px' }}
        aria-label={label}
        aria-expanded={!collapsed}
        title={label}
      >
        <span aria-hidden="true">
          {collapsed ? <PanelRightOpen size={14} /> : <PanelRightClose size={14} />}
        </span>
      </button>
    );
  }
  const placement: CSSProperties =
    position === 'right'
      ? { right: '10px', top: '10px' }
      : position === 'left'
        ? { left: '2%', top: '20px' }
        : position === 'top'
          ? { top: '2%', right: '50%', transform: 'translateX(50%)' }
          : { bottom: '2%', right: '50%', transform: 'translateX(50%)' };
  const icon =
    position === 'right' ? (
      collapsed ? (
        <ChevronRight size={12} />
      ) : (
        <ChevronLeft size={12} />
      )
    ) : position === 'left' ? (
      collapsed ? (
        <ChevronLeft size={12} />
      ) : (
        <ChevronRight size={12} />
      )
    ) : position === 'top' ? (
      collapsed ? (
        <ChevronUp size={12} />
      ) : (
        <ChevronDown size={12} />
      )
    ) : collapsed ? (
      <ChevronDown size={12} />
    ) : (
      <ChevronUp size={12} />
    );
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`legend-collapse-button is-floating ${className}`.trim()}
      style={{ width: '24px', height: '24px', ...placement }}
      aria-label={label}
    >
      <span aria-hidden="true">{icon}</span>
    </button>
  );
}
