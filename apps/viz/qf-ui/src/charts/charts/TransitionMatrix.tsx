/**
 * Generic probability transition matrix.
 *
 * USAGE:
 *   <TransitionMatrix regimes={['A', 'B']} matrix={matrix} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Heatmap } from './Heatmap';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface TransitionMatrixCell {
  count: number;
  probability: number;
}

export interface TransitionMatrixProps {
  regimes: readonly (string | number)[];
  matrix: readonly (readonly TransitionMatrixCell[])[];
  ariaLabel?: string | undefined;
  height?: number | string | undefined;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function TransitionMatrix({
  regimes,
  matrix,
  ariaLabel = 'Transition Matrix',
  height,
}: TransitionMatrixProps) {
  const labels = regimes.map(String);
  const cells = labels.flatMap((fromRegime, y) =>
    labels.map((toRegime, x) => {
      const cell = matrix[y]?.[x] ?? { count: 0, probability: 0 };
      const mix = 14 + Math.min(cell.probability, 1) * 64;
      return {
        x,
        y,
        value: cell.probability,
        display: `${(cell.probability * 100).toFixed(1)}%\n(${cell.count})`,
        tooltip: `${fromRegime} → ${toRegime}: ${(cell.probability * 100).toFixed(1)}% (${cell.count})`,
        color: `color-mix(in oklch, var(--qf-chart-series-primary) ${mix}%, var(--qf-chart-surface))`,
      };
    }),
  );
  return (
    <Heatmap
      xLabels={labels}
      yLabels={labels}
      cells={cells}
      height={height}
      ariaLabel={ariaLabel}
    />
  );
}
