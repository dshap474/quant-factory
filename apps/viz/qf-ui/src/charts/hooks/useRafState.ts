/**
 * React state whose queued updates are collapsed to one per animation frame.
 *
 * USAGE:
 *   const [hover, scheduleHover, clearHover] = useRafState<Hover | null>(null);
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useEffect, useRef, useState } from 'react';

// --------------------------------------------------------------------------- #
// State
// --------------------------------------------------------------------------- #

export function useRafState<T>(initialValue: T) {
  const [value, setValue] = useState(initialValue);
  const frameRef = useRef<number | null>(null);
  const pendingRef = useRef(initialValue);

  const schedule = (nextValue: T) => {
    pendingRef.current = nextValue;
    if (frameRef.current !== null) return;
    // A frame that fires synchronously (test shims) must not leave a stale handle behind.
    let settled = false;
    const frame = window.requestAnimationFrame(() => {
      settled = true;
      frameRef.current = null;
      setValue(pendingRef.current);
    });
    if (!settled) frameRef.current = frame;
  };

  const flush = (nextValue: T) => {
    if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
    frameRef.current = null;
    pendingRef.current = nextValue;
    setValue(nextValue);
  };

  useEffect(
    () => () => {
      if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
    },
    [],
  );

  return [value, schedule, flush] as const;
}
