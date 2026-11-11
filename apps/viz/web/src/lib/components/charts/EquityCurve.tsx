/**
 * Strategy equity data adapter to the shared qf-charts time-series component.
 *
 * USAGE: <EquityCurve data={pointsInPercentagePoints} title="Equity curve" />
 */

// --------------------------------------------------------------------------- #
// Imports and contract
// --------------------------------------------------------------------------- #

import { type MultiSeriesPoint, MultiSeriesTimeChart } from '@quant-factory/qf-ui/charts/renderers';

export interface EquityCurveProps {
  data: MultiSeriesPoint[];
  title?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function EquityCurve({ data, title = 'Equity curve' }: EquityCurveProps) {
  return (
    <MultiSeriesTimeChart
      title={title}
      valueFormat="percent-points"
      series={[
        {
          metric: 'strategy',
          axis: 'left',
          label: 'Strategy',
          points: data.map((point) => ({ x: point.date, y: point.value })),
        },
      ]}
    />
  );
}
