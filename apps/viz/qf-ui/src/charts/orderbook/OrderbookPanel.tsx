/**
 * Complete portable orderbook workspace with controlled state and host-supplied data.
 * USAGE: <OrderbookPanel controls={controls} heatmap={heatmapSource} depth={depthSource}
 *   historical={baselineSource} selectedIndex={index} onSelect={setIndex}
 *   depthMode={mode} onDepthModeChange={setMode} />
 */

// --------------------------------------------------------------------------- #
// Imports and public contracts
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { Button } from '../../primitives/Button';
import { SegmentedControl } from '../../primitives/SegmentedControl';
import { Text } from '../../primitives/Text';
import {
  OrderbookDepthChart,
  type OrderbookHeatmapData,
  type OrderbookHistoricalScale,
  type OrderbookLevel,
  OrderbookLiquidityChart,
} from '../charts/OrderbookChart';
import { ChartFrame } from '../components/ChartFrame';
import { ChartState } from '../components/ChartState';
import { OrderbookChartControls, type OrderbookChartControlsProps } from './OrderbookChartControls';

export type OrderbookDepthMode = 'cumulative' | 'band';
export interface OrderbookPanelData extends OrderbookHeatmapData {
  first: number | null;
  last: number | null;
  start: number | null;
  end: number | null;
  snapshot_count: number;
}
export interface OrderbookPanelSource<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  onRetry?: () => void;
}
export interface OrderbookPanelProps {
  controls: Omit<OrderbookChartControlsProps, 'first' | 'last'>;
  heatmap: OrderbookPanelSource<OrderbookPanelData>;
  depth: OrderbookPanelSource<readonly OrderbookLevel[]>;
  historical: OrderbookPanelSource<OrderbookHistoricalScale>;
  selectedIndex: number;
  onSelect: (index: number) => void;
  depthMode: OrderbookDepthMode;
  onDepthModeChange: (mode: OrderbookDepthMode) => void;
  title?: string;
  sizeLabel?: string;
  note?: ReactNode;
}

// --------------------------------------------------------------------------- #
// Source status and formatting
// --------------------------------------------------------------------------- #

interface SourceStateProps {
  source: OrderbookPanelSource<unknown>;
  children: ReactNode;
}
function SourceState({ source, children }: SourceStateProps) {
  if (source.error)
    return (
      <ChartState
        status="error"
        message={source.error}
        action={
          source.onRetry ? (
            <Button variant="control" onClick={source.onRetry}>
              Retry
            </Button>
          ) : undefined
        }
      />
    );
  if (source.loading) return <ChartState status="loading" message="Loading orderbook data" />;
  if (!source.data) return <ChartState status="empty" message="No orderbook data available" />;
  return children;
}
function utcLabel(timestamp: number | null): string {
  return timestamp === null
    ? ''
    : new Date(timestamp * 1000).toISOString().slice(0, 16).replace('T', ' ');
}

// --------------------------------------------------------------------------- #
// Combined panel
// --------------------------------------------------------------------------- #

export function OrderbookPanel({
  controls,
  heatmap,
  depth,
  historical,
  selectedIndex,
  onSelect,
  depthMode,
  onDepthModeChange,
  title = 'Orderbook liquidity',
  sizeLabel,
  note,
}: OrderbookPanelProps) {
  const data = heatmap.data;
  const index = Math.max(0, Math.min(selectedIndex, (data?.snapshots.length ?? 1) - 1));
  const snapshot = data?.snapshots[index];
  const mode = controls.scaleMode ?? 'relative';
  const chart =
    data && snapshot ? (
      <OrderbookLiquidityChart
        data={data}
        selectedIndex={index}
        onSelect={onSelect}
        scaleMode={mode}
        ariaLabel={title}
        {...(sizeLabel ? { sizeLabel } : {})}
        {...(historical.data ? { historicalScale: historical.data } : {})}
      />
    ) : (
      <ChartState status="empty" message="No snapshots in this window" />
    );
  return (
    <div className="qf-orderbook-panel">
      <OrderbookChartControls
        {...controls}
        start={data?.start ?? controls.start}
        first={data?.first ?? null}
        last={data?.last ?? null}
      />
      <ChartFrame
        title={title}
        subtitle={data ? `${utcLabel(data.start)} – ${utcLabel(data.end)} UTC` : undefined}
        footer={
          data
            ? `${data.snapshots.length} of ${data.snapshot_count} books · ${data.price_step} price units/bin · ${mode === 'relative' ? 'Relative: window maximum' : 'Historical: same-family percentiles'} · Click or use ← → to inspect depth`
            : undefined
        }
      >
        <SourceState source={heatmap}>
          {mode === 'historical' ? <SourceState source={historical}>{chart}</SourceState> : chart}
        </SourceState>
      </ChartFrame>
      {snapshot ? (
        <ChartFrame
          title="Selected snapshot depth"
          subtitle={`${utcLabel(snapshot.timestamp)} UTC · Mid ${snapshot.midprice.toLocaleString(undefined, { maximumFractionDigits: 2 })}`}
          actions={
            <SegmentedControl<OrderbookDepthMode>
              ariaLabel="Depth display"
              value={depthMode}
              options={[
                { value: 'cumulative', label: 'Cumulative' },
                { value: 'band', label: 'Per band' },
              ]}
              onValueChange={onDepthModeChange}
            />
          }
          footer={`${depth.data?.length ?? '…'} stored price bands · Full book, independent of heatmap range`}
        >
          <SourceState source={depth}>
            {depth.data ? (
              <OrderbookDepthChart
                levels={depth.data}
                midprice={snapshot.midprice}
                cumulative={depthMode === 'cumulative'}
              />
            ) : null}
          </SourceState>
        </ChartFrame>
      ) : null}
      {note ? (
        <Text variant="caption" tone="muted">
          {note}
        </Text>
      ) : null}
    </div>
  );
}
