/**
 * Toaster that costs nothing until the first `toast()` call: it renders null,
 * then lazily loads the Base UI renderer (Toast.tsx) and flushes the buffered
 * toasts. Mount this in the shell instead of `<Toaster />` to keep Base UI out
 * of the first-load bundle.
 *
 * USAGE:
 *   <LazyToaster />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Suspense, useSyncExternalStore } from 'react';

import { lazyNamed } from '../lib/lazy-named';

import { subscribeToastRequests, toastRequested } from './toast-store';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

const Toaster = lazyNamed(() => import('./Toast'), 'Toaster');

export function LazyToaster() {
  const requested = useSyncExternalStore(subscribeToastRequests, toastRequested, () => false);
  if (!requested) return null;
  return (
    <Suspense fallback={null}>
      <Toaster />
    </Suspense>
  );
}
