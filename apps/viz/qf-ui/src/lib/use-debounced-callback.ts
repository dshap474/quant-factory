/**
 * Trailing-edge debounced callback hook for input-driven side effects.
 *
 * USAGE:
 *   import { useDebouncedCallback } from '@quant-factory/qf-ui';
 *   const debounced = useDebouncedCallback((q: string) => onUpdate({ q }), 250);
 *   debounced('btc');        // fires once, 250ms after the last call
 *   debounced.cancel();      // drops any pending invocation
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useEffect, useMemo, useRef } from 'react';

// --------------------------------------------------------------------------- #
// Hook
// --------------------------------------------------------------------------- #

export type DebouncedCallback<Args extends unknown[]> = ((...args: Args) => void) & {
  cancel: () => void;
};

/** Debounce `callback` on the trailing edge; pending calls die with the component. */
export function useDebouncedCallback<Args extends unknown[]>(
  callback: (...args: Args) => void,
  delayMs: number,
): DebouncedCallback<Args> {
  const callbackRef = useRef(callback);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    callbackRef.current = callback;
  });

  useEffect(
    () => () => {
      if (timerRef.current !== null) clearTimeout(timerRef.current);
    },
    [],
  );

  return useMemo(() => {
    const run = (...args: Args) => {
      if (timerRef.current !== null) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        callbackRef.current(...args);
      }, delayMs);
    };
    run.cancel = () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
    return run;
  }, [delayMs]);
}
