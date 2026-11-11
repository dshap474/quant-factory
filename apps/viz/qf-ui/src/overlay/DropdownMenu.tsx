/**
 * Action menu built on Base UI Menu: items, checkbox items, radio items,
 * labels, and separators. Arrow keys move the highlight, Enter or click
 * activates, Escape closes and returns focus to the trigger. Render your own
 * control as the trigger with the `render` prop.
 *
 * USAGE:
 *   <DropdownMenu>
 *     <DropdownMenuTrigger render={<Button variant="control" />}>Options</DropdownMenuTrigger>
 *     <DropdownMenuContent align="end">
 *       <DropdownMenuLabel>Run</DropdownMenuLabel>
 *       <DropdownMenuItem onClick={rename}>Rename</DropdownMenuItem>
 *       <DropdownMenuSeparator />
 *       <DropdownMenuCheckboxItem checked={pinned} onCheckedChange={setPinned}>
 *         Pinned
 *       </DropdownMenuCheckboxItem>
 *     </DropdownMenuContent>
 *   </DropdownMenu>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Menu as BaseMenu } from '@base-ui/react/menu';
import { Check, Circle } from 'lucide-react';
import type { ComponentPropsWithRef } from 'react';
import { cn } from '../lib/cn';
import { ICON_SIZE, ICON_STROKE } from '../lib/icon';
import { OVERLAY_SIDE_OFFSET, type OverlayPlacementProps } from './placement';

import './Overlay.css';
import './DropdownMenu.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type DropdownMenuProps = ComponentPropsWithRef<typeof BaseMenu.Root>;

export type DropdownMenuTriggerProps = ComponentPropsWithRef<typeof BaseMenu.Trigger>;

export interface DropdownMenuContentProps
  extends Omit<ComponentPropsWithRef<typeof BaseMenu.Popup>, 'className'>,
    OverlayPlacementProps {
  className?: string | undefined;
}

export interface DropdownMenuItemProps
  extends Omit<ComponentPropsWithRef<typeof BaseMenu.Item>, 'className'> {
  className?: string | undefined;
}

export interface DropdownMenuCheckboxItemProps
  extends Omit<ComponentPropsWithRef<typeof BaseMenu.CheckboxItem>, 'className'> {
  className?: string | undefined;
}

export type DropdownMenuRadioGroupProps = ComponentPropsWithRef<typeof BaseMenu.RadioGroup>;

export interface DropdownMenuRadioItemProps
  extends Omit<ComponentPropsWithRef<typeof BaseMenu.RadioItem>, 'className'> {
  className?: string | undefined;
}

export interface DropdownMenuLabelProps extends ComponentPropsWithRef<'div'> {}

export interface DropdownMenuSeparatorProps
  extends Omit<ComponentPropsWithRef<typeof BaseMenu.Separator>, 'className'> {
  className?: string | undefined;
}

// --------------------------------------------------------------------------- #
// Components
// --------------------------------------------------------------------------- #

export function DropdownMenu(props: DropdownMenuProps) {
  return <BaseMenu.Root {...props} />;
}

export function DropdownMenuTrigger(props: DropdownMenuTriggerProps) {
  return <BaseMenu.Trigger {...props} />;
}

export function DropdownMenuContent({
  side = 'bottom',
  align = 'start',
  sideOffset = OVERLAY_SIDE_OFFSET,
  alignOffset,
  className,
  ...props
}: DropdownMenuContentProps) {
  return (
    <BaseMenu.Portal>
      <BaseMenu.Positioner
        className="ui-overlay-positioner"
        side={side}
        align={align}
        sideOffset={sideOffset}
        alignOffset={alignOffset}
      >
        <BaseMenu.Popup
          className={cn('ui-overlay-surface', 'ui-menu', 'qf-motion-pop', className)}
          {...props}
        />
      </BaseMenu.Positioner>
    </BaseMenu.Portal>
  );
}

export function DropdownMenuItem({ className, ...props }: DropdownMenuItemProps) {
  return <BaseMenu.Item className={cn('ui-menu-item', className)} {...props} />;
}

export function DropdownMenuCheckboxItem({
  className,
  children,
  ...props
}: DropdownMenuCheckboxItemProps) {
  return (
    <BaseMenu.CheckboxItem className={cn('ui-menu-item has-indicator', className)} {...props}>
      <span className="ui-menu-indicator">
        <BaseMenu.CheckboxItemIndicator>
          <Check aria-hidden="true" size={ICON_SIZE} strokeWidth={ICON_STROKE} />
        </BaseMenu.CheckboxItemIndicator>
      </span>
      {children}
    </BaseMenu.CheckboxItem>
  );
}

export function DropdownMenuRadioGroup(props: DropdownMenuRadioGroupProps) {
  return <BaseMenu.RadioGroup {...props} />;
}

export function DropdownMenuRadioItem({
  className,
  children,
  ...props
}: DropdownMenuRadioItemProps) {
  return (
    <BaseMenu.RadioItem className={cn('ui-menu-item has-indicator', className)} {...props}>
      <span className="ui-menu-indicator">
        <BaseMenu.RadioItemIndicator>
          <Circle aria-hidden="true" fill="currentColor" size={8} />
        </BaseMenu.RadioItemIndicator>
      </span>
      {children}
    </BaseMenu.RadioItem>
  );
}

export function DropdownMenuLabel({ className, ...props }: DropdownMenuLabelProps) {
  return <div className={cn('ui-menu-label', className)} {...props} />;
}

export function DropdownMenuSeparator({ className, ...props }: DropdownMenuSeparatorProps) {
  return <BaseMenu.Separator className={cn('ui-menu-separator', className)} {...props} />;
}
