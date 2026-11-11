/**
 * Toast renderer built on Base UI Toast. Mount `<Toaster />` (or `<LazyToaster />`,
 * which defers this module until the first toast) once near the app root; call
 * `toast({ title, description?, tone? })` from anywhere via toast-store.ts
 * (`useToast()` in components or the exported `toast` function outside React).
 * Toasts stack bottom-right, auto-dismiss after 4s (`durationMs` overrides;
 * `0` keeps it until closed), and announce politely (critical announces
 * urgently).
 *
 * USAGE:
 *   // once, in the shell
 *   <Toaster />
 *
 *   // anywhere
 *   const { toast } = useToast();
 *   await navigator.clipboard.writeText(id);
 *   toast({ title: 'Copied', description: id, tone: 'success' });
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Toast as BaseToast } from '@base-ui/react/toast';
import { X } from 'lucide-react';
import { type ReactNode, useEffect } from 'react';
import { ICON_SIZE, ICON_STROKE } from '../lib/icon';

import type { Tone } from '../lib/tone';
import { registerToastSink, type ToastInput } from './toast-store';

import './Overlay.css';
import './Toast.css';

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

/** Auto-dismiss delay in ms. */
export const TOAST_DURATION_MS = 4000;

/** Most toasts shown at once; older ones are marked limited and dropped. */
export const TOAST_LIMIT = 3;

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ToastData {
  tone: Tone;
}

export interface ToastProviderProps {
  children?: ReactNode;
}

// --------------------------------------------------------------------------- #
// Manager
// --------------------------------------------------------------------------- #

const toastManager = BaseToast.createToastManager<ToastData>();

/** Bridge from the dependency-free store into the Base UI manager. */
const TOAST_SINK = {
  add(id: string, { title, description, tone = 'neutral', durationMs }: ToastInput) {
    toastManager.add({
      id,
      title,
      description,
      type: tone,
      data: { tone },
      priority: tone === 'critical' ? 'high' : 'low',
      ...(durationMs !== undefined ? { timeout: durationMs } : {}),
    });
  },
  close(id?: string) {
    toastManager.close(id);
  },
};

// --------------------------------------------------------------------------- #
// Components
// --------------------------------------------------------------------------- #

function ToastList() {
  const { toasts } = BaseToast.useToastManager<ToastData>();

  return (
    <BaseToast.Portal>
      <BaseToast.Viewport className="ui-toast-viewport">
        {toasts.map((item) => (
          <BaseToast.Root
            key={item.id}
            toast={item}
            className="ui-toast qf-motion-sheet-bottom"
            data-tone={item.data?.tone ?? 'neutral'}
          >
            {item.title ? <BaseToast.Title className="ui-toast-title" /> : null}
            {item.description ? <BaseToast.Description className="ui-toast-description" /> : null}
            <BaseToast.Close className="ui-overlay-close" aria-label="Dismiss">
              <X aria-hidden="true" size={ICON_SIZE} strokeWidth={ICON_STROKE} />
            </BaseToast.Close>
          </BaseToast.Root>
        ))}
      </BaseToast.Viewport>
    </BaseToast.Portal>
  );
}

/** Provider bound to the shared toast manager; `Toaster` already includes one. */
export function ToastProvider({ children }: ToastProviderProps) {
  return (
    <BaseToast.Provider toastManager={toastManager} timeout={TOAST_DURATION_MS} limit={TOAST_LIMIT}>
      {children}
    </BaseToast.Provider>
  );
}

/** Renders the bottom-right toast stack; mount once near the app root. */
export function Toaster() {
  useEffect(() => registerToastSink(TOAST_SINK), []);
  return (
    <ToastProvider>
      <ToastList />
    </ToastProvider>
  );
}
