/**
 * Dependency-free toast front door. `toast()` and `useToast()` live here so
 * callers never pull Base UI into their chunk; the Base UI renderer in
 * Toast.tsx registers itself as the sink when `<Toaster />` mounts, and toasts
 * raised before that are buffered and flushed on registration. `LazyToaster`
 * subscribes to `toastRequested()` to load the renderer on the first toast.
 *
 * USAGE:
 *   const { toast } = useToast();
 *   toast({ title: 'Copied', description: id, tone: 'success' });
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import type { Tone } from '../lib/tone';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ToastInput {
  title: ReactNode;
  description?: ReactNode | undefined;
  /** Colour family (default `neutral`). */
  tone?: Tone | undefined;
  /** Auto-dismiss delay in ms; `0` disables auto-dismiss. */
  durationMs?: number | undefined;
}

export interface UseToastResult {
  /** Show a toast; returns its id. */
  toast: (input: ToastInput) => string;
  /** Close one toast by id, or all when omitted. */
  dismiss: (id?: string) => void;
}

/** The renderer that actually shows toasts; registered by `<Toaster />`. */
export interface ToastSink {
  add: (id: string, input: ToastInput) => void;
  close: (id?: string) => void;
}

// --------------------------------------------------------------------------- #
// Store
// --------------------------------------------------------------------------- #

let sink: ToastSink | null = null;
let pending: Array<{ id: string; input: ToastInput }> = [];
let requested = false;
let sequence = 0;
const listeners = new Set<() => void>();

/** Show a toast from anywhere; buffered until a `<Toaster />` mounts. Returns its id. */
export function toast(input: ToastInput): string {
  sequence += 1;
  const id = `qf-toast-${sequence}`;
  if (sink) {
    sink.add(id, input);
  } else {
    pending.push({ id, input });
  }
  if (!requested) {
    requested = true;
    for (const listener of listeners) listener();
  }
  return id;
}

/** Close one toast by id, or all when omitted. */
export function dismissToast(id?: string): void {
  if (sink) {
    sink.close(id);
    return;
  }
  pending = id === undefined ? [] : pending.filter((entry) => entry.id !== id);
}

const TOAST_API: UseToastResult = { toast, dismiss: dismissToast };

/** Stable handle for showing and closing toasts from components. */
export function useToast(): UseToastResult {
  return TOAST_API;
}

/** Register the renderer and flush buffered toasts; returns the unregister function. */
export function registerToastSink(next: ToastSink): () => void {
  sink = next;
  const buffered = pending;
  pending = [];
  for (const entry of buffered) next.add(entry.id, entry.input);
  return () => {
    if (sink === next) sink = null;
  };
}

/** True once any toast has been requested (drives `LazyToaster`). */
export function toastRequested(): boolean {
  return requested;
}

export function subscribeToastRequests(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
