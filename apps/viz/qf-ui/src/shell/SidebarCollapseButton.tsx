/**
 * Expand/collapse control for the app sidebar.
 *
 * USAGE:
 *   <SidebarCollapseButton collapsed={collapsed} label="Expand nav" onClick={toggle} />
 *   <SidebarCollapseButton side="right" collapsed={collapsed} label="Collapse rail" onClick={toggle} />
 *   <SidebarCollapseButton variant="icon" side="right" collapsed={collapsed} label="Collapse rail" onClick={toggle} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen } from 'lucide-react';
import { ICON_SIZE, ICON_STROKE } from '../lib/icon';
import { Button } from '../primitives/Button';
import './SidebarCollapseButton.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface SidebarCollapseButtonProps {
  collapsed: boolean;
  label: string;
  onClick: () => void;
  /** Edge the sidebar docks to; picks the left- or right-panel glyph pair. */
  side?: 'left' | 'right';
  /** Host geometry: footer bar (default), collapsed-navigator tile, or inline icon square. */
  variant?: 'bar' | 'tile' | 'icon';
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function SidebarCollapseButton({
  collapsed,
  label,
  onClick,
  side = 'left',
  variant = 'bar',
}: SidebarCollapseButtonProps) {
  const pointsRight = side === 'right' ? !collapsed : collapsed;
  const Glyph =
    side === 'right'
      ? collapsed
        ? PanelRightOpen
        : PanelRightClose
      : collapsed
        ? PanelLeftOpen
        : PanelLeftClose;
  return (
    <Button
      type="button"
      className={`sidebar-collapse-button is-${variant}`}
      aria-label={label}
      title={label}
      onClick={onClick}
    >
      <span className="sidebar-collapse-icon-slot" aria-hidden="true">
        <span
          className="sidebar-collapse-glyph"
          data-direction={pointsRight ? 'right' : 'left'}
          aria-hidden="true"
        >
          <Glyph size={ICON_SIZE} strokeWidth={ICON_STROKE} />
        </span>
      </span>
    </Button>
  );
}
