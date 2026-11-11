/**
 * Hover and focus hint built on Base UI Tooltip. `Tooltip` is the simple form
 * (a `content` string or node plus one trigger child); the `TooltipRoot` /
 * `TooltipTrigger` / `TooltipContent` parts compose custom layouts. Wrap a
 * region in `TooltipProvider` so a second tooltip opens instantly right after
 * the first closes. Tooltips are visual hints only: put essential text in the
 * page, and use `InfoTip` where touch or keyboard access matters.
 *
 * USAGE:
 *   <TooltipProvider>
 *     <Tooltip content="Refresh data">
 *       <Button variant="control" aria-label="Refresh"><RefreshCw size={16} /></Button>
 *     </Tooltip>
 *   </TooltipProvider>
 *
 *   <TooltipRoot>
 *     <TooltipTrigger render={<span />}>Sharpe</TooltipTrigger>
 *     <TooltipContent side="bottom">Annualised, net of cost</TooltipContent>
 *   </TooltipRoot>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Tooltip as BaseTooltip } from '@base-ui/react/tooltip';
import type { ComponentPropsWithRef, ReactElement, ReactNode } from 'react';

import { cn } from '../lib/cn';
import { OVERLAY_SIDE_OFFSET, type OverlayPlacementProps } from './placement';

import './Overlay.css';
import './Tooltip.css';

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

/** Hover delay before a tooltip opens. */
export const TOOLTIP_OPEN_DELAY_MS = 400;

/** A tooltip opening within this window of another closing opens instantly. */
export const TOOLTIP_GROUP_TIMEOUT_MS = 400;

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface TooltipProviderProps {
  /** Hover delay in ms for every tooltip in the group (default 400). */
  delay?: number | undefined;
  /** Window in ms during which a neighbouring tooltip opens instantly (default 400). */
  timeout?: number | undefined;
  children?: ReactNode;
}

export type TooltipRootProps = ComponentPropsWithRef<typeof BaseTooltip.Root>;

export type TooltipTriggerProps = ComponentPropsWithRef<typeof BaseTooltip.Trigger>;

export interface TooltipContentProps
  extends Omit<ComponentPropsWithRef<typeof BaseTooltip.Popup>, 'className'>,
    OverlayPlacementProps {
  className?: string | undefined;
}

export interface TooltipProps extends OverlayPlacementProps {
  /** Hint text or node shown in the popup. */
  content: ReactNode;
  /** The single element the tooltip is anchored to; it receives the trigger props. */
  children: ReactElement<Record<string, unknown>>;
  /** Hover delay in ms (default 400). */
  delay?: number | undefined;
  /** Suppress the tooltip without changing the trigger. */
  disabled?: boolean | undefined;
  className?: string | undefined;
}

// --------------------------------------------------------------------------- #
// Parts
// --------------------------------------------------------------------------- #

export function TooltipProvider({
  delay = TOOLTIP_OPEN_DELAY_MS,
  timeout = TOOLTIP_GROUP_TIMEOUT_MS,
  children,
}: TooltipProviderProps) {
  return (
    <BaseTooltip.Provider delay={delay} timeout={timeout}>
      {children}
    </BaseTooltip.Provider>
  );
}

export function TooltipRoot(props: TooltipRootProps) {
  return <BaseTooltip.Root {...props} />;
}

export function TooltipTrigger(props: TooltipTriggerProps) {
  return <BaseTooltip.Trigger {...props} />;
}

export function TooltipContent({
  side = 'top',
  align = 'center',
  sideOffset = OVERLAY_SIDE_OFFSET,
  alignOffset,
  className,
  ...props
}: TooltipContentProps) {
  return (
    <BaseTooltip.Portal>
      <BaseTooltip.Positioner
        className="ui-overlay-positioner"
        side={side}
        align={align}
        sideOffset={sideOffset}
        alignOffset={alignOffset}
      >
        <BaseTooltip.Popup
          className={cn('ui-overlay-surface', 'ui-tooltip', 'qf-motion-pop', className)}
          {...props}
        />
      </BaseTooltip.Positioner>
    </BaseTooltip.Portal>
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Tooltip({
  content,
  children,
  delay = TOOLTIP_OPEN_DELAY_MS,
  disabled,
  className,
  side,
  align,
  sideOffset,
  alignOffset,
}: TooltipProps) {
  return (
    <TooltipRoot>
      <TooltipTrigger render={children} delay={delay} disabled={disabled} />
      <TooltipContent
        className={className}
        side={side}
        align={align}
        sideOffset={sideOffset}
        alignOffset={alignOffset}
      >
        {content}
      </TooltipContent>
    </TooltipRoot>
  );
}
