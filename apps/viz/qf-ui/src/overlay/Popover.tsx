/**
 * Anchored floating panel built on Base UI Popover. Click or keyboard opens it,
 * Escape and outside press close it, and focus returns to the trigger. Compose
 * the parts; render your own control as the trigger with the `render` prop.
 *
 * USAGE:
 *   <Popover>
 *     <PopoverTrigger render={<Button variant="control" />}>Filters</PopoverTrigger>
 *     <PopoverContent align="start">
 *       <PopoverTitle>Filters</PopoverTitle>
 *       <PopoverDescription>Narrow the run list.</PopoverDescription>
 *     </PopoverContent>
 *   </Popover>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Popover as BasePopover } from '@base-ui/react/popover';
import type { ComponentPropsWithRef } from 'react';

import { cn } from '../lib/cn';
import { OVERLAY_SIDE_OFFSET, type OverlayPlacementProps } from './placement';

import './Overlay.css';
import './Popover.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type PopoverProps = ComponentPropsWithRef<typeof BasePopover.Root>;

export type PopoverTriggerProps = ComponentPropsWithRef<typeof BasePopover.Trigger>;

export interface PopoverContentProps
  extends Omit<ComponentPropsWithRef<typeof BasePopover.Popup>, 'className'>,
    OverlayPlacementProps {
  className?: string | undefined;
}

export interface PopoverTitleProps
  extends Omit<ComponentPropsWithRef<typeof BasePopover.Title>, 'className'> {
  className?: string | undefined;
}

export interface PopoverDescriptionProps
  extends Omit<ComponentPropsWithRef<typeof BasePopover.Description>, 'className'> {
  className?: string | undefined;
}

export type PopoverCloseProps = ComponentPropsWithRef<typeof BasePopover.Close>;

// --------------------------------------------------------------------------- #
// Components
// --------------------------------------------------------------------------- #

export function Popover(props: PopoverProps) {
  return <BasePopover.Root {...props} />;
}

export function PopoverTrigger(props: PopoverTriggerProps) {
  return <BasePopover.Trigger {...props} />;
}

export function PopoverContent({
  side = 'bottom',
  align = 'center',
  sideOffset = OVERLAY_SIDE_OFFSET,
  alignOffset,
  className,
  ...props
}: PopoverContentProps) {
  return (
    <BasePopover.Portal>
      <BasePopover.Positioner
        className="ui-overlay-positioner"
        side={side}
        align={align}
        sideOffset={sideOffset}
        alignOffset={alignOffset}
      >
        <BasePopover.Popup
          className={cn('ui-overlay-surface', 'ui-popover', 'qf-motion-pop', className)}
          {...props}
        />
      </BasePopover.Positioner>
    </BasePopover.Portal>
  );
}

export function PopoverTitle({ className, ...props }: PopoverTitleProps) {
  return <BasePopover.Title className={cn('ui-popover-title', className)} {...props} />;
}

export function PopoverDescription({ className, ...props }: PopoverDescriptionProps) {
  return <BasePopover.Description className={cn('ui-popover-description', className)} {...props} />;
}

export function PopoverClose(props: PopoverCloseProps) {
  return <BasePopover.Close {...props} />;
}
