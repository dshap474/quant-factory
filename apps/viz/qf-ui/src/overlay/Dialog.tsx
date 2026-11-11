/**
 * Modal dialog built on Base UI Dialog. `Dialog` is the complete form: title and
 * description are required (they wire aria-labelledby / aria-describedby), body
 * is `children`, and `footer` is an optional action row. Focus is trapped,
 * Escape and backdrop press close, and focus returns to the trigger. The
 * `DialogRoot` / `DialogTrigger` / `DialogContent` parts compose custom layouts
 * and are reused by `Sheet`.
 *
 * USAGE:
 *   <Dialog
 *     trigger={<Button variant="control" />}
 *     triggerLabel="Rename"
 *     title="Rename run"
 *     description="The new name replaces the label in every list."
 *     footer={<DialogClose render={<Button variant="control" />}>Cancel</DialogClose>}
 *   >
 *     <Input value={name} onChange={rename} />
 *   </Dialog>
 *
 *   <Dialog open={open} onOpenChange={setOpen} title="Delete?" description="Cannot be undone." />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Dialog as BaseDialog } from '@base-ui/react/dialog';
import { X } from 'lucide-react';
import type { ComponentPropsWithRef, ReactElement, ReactNode } from 'react';
import { cn } from '../lib/cn';
import { ICON_SIZE, ICON_STROKE } from '../lib/icon';

import './Overlay.css';
import './Dialog.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type DialogSize = 'sm' | 'md' | 'lg';

export type DialogRootProps = ComponentPropsWithRef<typeof BaseDialog.Root>;

export type DialogTriggerProps = ComponentPropsWithRef<typeof BaseDialog.Trigger>;

export type DialogCloseProps = ComponentPropsWithRef<typeof BaseDialog.Close>;

export interface DialogContentProps
  extends Omit<ComponentPropsWithRef<typeof BaseDialog.Popup>, 'className'> {
  size?: DialogSize | undefined;
  className?: string | undefined;
}

export interface DialogTitleProps
  extends Omit<ComponentPropsWithRef<typeof BaseDialog.Title>, 'className'> {
  className?: string | undefined;
}

export interface DialogDescriptionProps
  extends Omit<ComponentPropsWithRef<typeof BaseDialog.Description>, 'className'> {
  className?: string | undefined;
}

export interface DialogFooterProps extends ComponentPropsWithRef<'div'> {}

export interface DialogProps
  extends Pick<
    DialogRootProps,
    'open' | 'defaultOpen' | 'onOpenChange' | 'modal' | 'disablePointerDismissal'
  > {
  /** Dialog heading; also the accessible name. */
  title: ReactNode;
  /** Short explanation; also the accessible description. */
  description: ReactNode;
  /** Optional action row, right-aligned under the body. */
  footer?: ReactNode;
  /** Optional trigger element (rendered through Base UI `render`); label goes in `triggerLabel`. */
  trigger?: ReactElement<Record<string, unknown>> | undefined;
  /** Children of the trigger element. */
  triggerLabel?: ReactNode;
  size?: DialogSize | undefined;
  className?: string | undefined;
  children?: ReactNode;
}

// --------------------------------------------------------------------------- #
// Parts
// --------------------------------------------------------------------------- #

export function DialogRoot(props: DialogRootProps) {
  return <BaseDialog.Root {...props} />;
}

export function DialogTrigger(props: DialogTriggerProps) {
  return <BaseDialog.Trigger {...props} />;
}

export function DialogClose(props: DialogCloseProps) {
  return <BaseDialog.Close {...props} />;
}

export function DialogTitle({ className, ...props }: DialogTitleProps) {
  return <BaseDialog.Title className={cn('ui-dialog-title', className)} {...props} />;
}

export function DialogDescription({ className, ...props }: DialogDescriptionProps) {
  return <BaseDialog.Description className={cn('ui-dialog-description', className)} {...props} />;
}

export function DialogFooter({ className, ...props }: DialogFooterProps) {
  return <div className={cn('ui-dialog-footer', className)} {...props} />;
}

/** Portal + backdrop + centred popup with the corner close button. */
export function DialogContent({ size = 'md', className, children, ...props }: DialogContentProps) {
  return (
    <BaseDialog.Portal>
      <BaseDialog.Backdrop className="ui-overlay-backdrop qf-motion-fade" />
      <BaseDialog.Popup
        className={cn(
          'ui-overlay-surface',
          'ui-dialog',
          'qf-motion-pop',
          size !== 'md' && `is-${size}`,
          className,
        )}
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

export function Dialog({
  title,
  description,
  footer,
  trigger,
  triggerLabel,
  size,
  className,
  children,
  ...rootProps
}: DialogProps) {
  return (
    <DialogRoot {...rootProps}>
      {trigger ? <DialogTrigger render={trigger}>{triggerLabel}</DialogTrigger> : null}
      <DialogContent size={size} className={className}>
        <div className="ui-dialog-header">
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </div>
        {children ? <div className="ui-dialog-body">{children}</div> : null}
        {footer ? <DialogFooter>{footer}</DialogFooter> : null}
      </DialogContent>
    </DialogRoot>
  );
}
