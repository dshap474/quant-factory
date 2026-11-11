/**
 * Observe a chart host and return clamped plot geometry.
 *
 * USAGE:
 *   const { ref, width, height } = useResponsiveChart({ aspectRatio: 16 / 9 });
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useEffect, useRef, useState } from 'react';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ResponsiveChartOptions {
  aspectRatio?: number;
  minWidth?: number;
  minHeight?: number;
}

export interface ResponsiveChartResult {
  ref: React.RefObject<HTMLDivElement | null>;
  width: number;
  height: number;
}

// --------------------------------------------------------------------------- #
// Hook
// --------------------------------------------------------------------------- #

export function useResponsiveChart({
  aspectRatio = 16 / 9,
  minWidth = 1,
  minHeight = 1,
}: ResponsiveChartOptions = {}): ResponsiveChartResult {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: minWidth, height: minHeight });
  useEffect(() => {
    const host = ref.current;
    if (!host) return;
    const update = (width: number) =>
      setSize({
        width: Math.max(minWidth, width),
        height: Math.max(minHeight, width / aspectRatio),
      });
    update(host.getBoundingClientRect().width);
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) update(entry.contentRect.width);
    });
    observer.observe(host);
    return () => observer.disconnect();
  }, [aspectRatio, minHeight, minWidth]);
  return { ref, ...size };
}
