/**
 * Small "i" icon button that opens a compact Popover of explanatory text. Unlike
 * a tooltip it opens on click, tap, or Enter/Space (and on hover), so the text
 * stays reachable on touch and keyboard.
 *
 * USAGE:
 *   <span>Funding rate <InfoTip content="8h annualised, median across venues." /></span>
 *   <InfoTip label="About turnover" content={<>Two-way, per rebalance.</>} side="right" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Info } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '../lib/cn';
import { ICON_SIZE_SM, ICON_STROKE } from '../lib/icon';
import { Popover, PopoverContent, PopoverTrigger } from './Popover';
import type { OverlayPlacementProps } from './placement';

import './InfoTip.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface InfoTipProps extends OverlayPlacementProps {
  /** Explanatory text or node shown in the popup. */
  content: ReactNode;
  /** Accessible name of the icon button (default "More info"). */
  label?: string | undefined;
  /** Also open on pointer hover (default true). */
  openOnHover?: boolean | undefined;
  className?: string | undefined;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function InfoTip({
  content,
  label = 'More info',
  openOnHover = true,
  className,
  side = 'top',
  align,
  sideOffset,
  alignOffset,
}: InfoTipProps) {
  return (
    <Popover>
      <PopoverTrigger
        type="button"
        aria-label={label}
        className={cn('ui-info-tip-trigger', className)}
        openOnHover={openOnHover}
        delay={200}
        closeDelay={100}
      >
        <Info aria-hidden="true" size={ICON_SIZE_SM} strokeWidth={ICON_STROKE} />
      </PopoverTrigger>
      <PopoverContent
        className="ui-info-tip"
        side={side}
        align={align}
        sideOffset={sideOffset}
        alignOffset={alignOffset}
      >
        {content}
      </PopoverContent>
    </Popover>
  );
}
