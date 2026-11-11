/**
 * Optional lifecycle recorder used by tests and low-cardinality diagnostics.
 *
 * USAGE:
 *   setLifecycleRecorder((event) => events.push(event));
 */

// --------------------------------------------------------------------------- #
// Types and state
// --------------------------------------------------------------------------- #

export type QfLifecycleEvent = 'init' | 'setOption' | 'resize' | 'dispose';
export type QfLifecycleRecorder = (event: QfLifecycleEvent) => void;

let recorder: QfLifecycleRecorder | null = null;

// --------------------------------------------------------------------------- #
// Recorder API
// --------------------------------------------------------------------------- #

export function setLifecycleRecorder(next: QfLifecycleRecorder | null): void {
  recorder = next;
}

export function recordLifecycle(event: QfLifecycleEvent): void {
  recorder?.(event);
}
