/**
 * Right-edge drawer: a Base UI Dialog variant that slides in from the right.
 * Same contract as `Dialog` (required title and description, optional footer,
 * focus trap, Escape and backdrop close); it reuses the Dialog root, trigger,
 * close, title, description, and footer parts.
 *
 * USAGE:
 *   <Sheet
 *     open={open}
 *     onOpenChange={setOpen}
 *     title="Run details"
 *     description="Inputs and outputs of the selected run."
 *   >
 *     <RunDetail id={id} />
 *   </Sheet>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Dialog as BaseDialog } from '@base-ui/react/dialog';
import { X } from 'lucide-react';
import type { ComponentPropsWithRef, ReactNode } from 'react';
import { cn } from '../lib/cn';
import { ICON_SIZE, ICON_STROKE } from '../lib/icon';
import {
  DialogDescription,
  DialogFooter,
  type DialogProps,
  DialogRoot,
  DialogTitle,
  DialogTrigger,
} from './Dialog';

import './Overlay.css';
import './Dialog.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface SheetContentProps
  extends Omit<ComponentPropsWithRef<typeof BaseDialog.Popup>, 'className'> {
  className?: string | undefined;
}

export interface SheetProps extends Omit<DialogProps, 'size'> {
  /** Reading width (44rem) for documents and tables; default 28rem. */
  wide?: boolean;
  children?: ReactNode;
}

// --------------------------------------------------------------------------- #
// Parts
// --------------------------------------------------------------------------- #

/** Portal + backdrop + right-edge popup with the corner close button. */
export function SheetContent({ className, children, ...props }: SheetContentProps) {
  return (
    <BaseDialog.Portal>
      <BaseDialog.Backdrop className="ui-overlay-backdrop qf-motion-fade" />
      <BaseDialog.Popup
        className={cn('ui-overlay-surface', 'ui-sheet', 'qf-motion-sheet-right', className)}
        {...props}
      >
        {children}
        <BaseDialog.Close className="ui-overlay-close" aria-label="Close">
          <X aria-hidden="true" size={ICON_SIZE} strokeWidth={ICON_STROKE} />
        </BaseDialog.Close>
      </BaseDialog.Popup>
    </BaseDialog.Portal>
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Sheet({
  title,
  description,
  footer,
  trigger,
  triggerLabel,
  wide = false,
  className,
  children,
  ...rootProps
}: SheetProps) {
  return (
    <DialogRoot {...rootProps}>
      {trigger ? <DialogTrigger render={trigger}>{triggerLabel}</DialogTrigger> : null}
      <SheetContent className={cn(wide && 'is-wide', className)}>
        <div className="ui-dialog-header">
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </div>
        {children ? <div className="ui-dialog-body">{children}</div> : null}
        {footer ? <DialogFooter>{footer}</DialogFooter> : null}
      </SheetContent>
    </DialogRoot>
  );
}
