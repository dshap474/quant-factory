/**
 * Viz data adapter for the portable qf orderbook panel, with saved per-file view state.
 * USAGE: <OrderbookChartWorkspace path={path} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { OrderbookPanel } from '@quant-factory/qf-ui/charts/orderbook';
import { useEffect, useState } from 'react';
import {
  useOrderbookDepth,
  useOrderbookHeatmap,
  useOrderbookHistoricalScale,
} from '@/lib/api/orderbook';
import { isLoadingData } from '@/ui';
import {
  loadOrderbookView,
  type OrderbookViewState,
  saveOrderbookView,
} from './orderbook-view-state';

// --------------------------------------------------------------------------- #
// Host adapter
// --------------------------------------------------------------------------- #

export function OrderbookChartWorkspace({ path }: { path: string }) {
  const [view, setView] = useState(() => loadOrderbookView(path));
  useEffect(() => saveOrderbookView(path, view), [path, view]);
  const updateView = (patch: Partial<OrderbookViewState>) =>
    setView((current) => ({ ...current, ...patch }));
  const heatmap = useOrderbookHeatmap(path, view.start, view.bandPercent, view.hours);
  const baseline = useOrderbookHistoricalScale(path, view.scaleMode === 'historical');
  const data = heatmap.data;
  const calibration = baseline.data;
  const match =
    data?.snapshots.findIndex(
      (book) =>
        book.timestamp === view.selected?.timestamp && book.midprice === view.selected.midprice,
    ) ?? -1;
  const selectedIndex = Math.max(0, match);
  // Disabled when the window has no snapshots: isLoadingData reads that as empty, not loading.
  const depth = useOrderbookDepth(path, data?.snapshots[selectedIndex]);
  const dateLabel = (timestamp: number) =>
    new Date(timestamp * 1000).toISOString().slice(0, 16).replace('T', ' ');
  return (
    <OrderbookPanel
      controls={{
        start: view.start,
        hours: view.hours,
        bandPercent: view.bandPercent,
        scaleMode: view.scaleMode,
        onStartChange: (start) => updateView({ start, selected: null }),
        onHoursChange: (hours) => updateView({ hours, selected: null }),
        onBandPercentChange: (bandPercent) => updateView({ bandPercent }),
        onScaleModeChange: (scaleMode) => updateView({ scaleMode }),
      }}
      heatmap={{
        data: data ?? null,
        loading: isLoadingData(heatmap),
        error: heatmap.error?.message ?? null,
        onRetry: () => void heatmap.refetch(),
      }}
      depth={{
        data: depth.data?.levels ?? null,
        loading: isLoadingData(depth),
        error: depth.error?.message ?? null,
        onRetry: () => void depth.refetch(),
      }}
      historical={{
        data: calibration
          ? {
              p50: calibration.p50,
              p90: calibration.p90,
              p95: calibration.p95,
              p99: calibration.p99,
              priceStep: calibration.price_step,
            }
          : null,
        loading: isLoadingData(baseline),
        error: baseline.error?.message ?? null,
        onRetry: () => void baseline.refetch(),
      }}
      selectedIndex={selectedIndex}
      onSelect={(index) => {
        const book = data?.snapshots[index];
        if (book) updateView({ selected: book });
      }}
      depthMode={view.depthMode}
      onDepthModeChange={(depthMode) => updateView({ depthMode })}
      note={`${view.scaleMode === 'historical' && calibration ? `Historical baseline: ${calibration.sample_books} sampled books across ${calibration.partitions} monthly files, ${dateLabel(calibration.first)}–${dateLabel(calibration.last)} UTC; populated 100-unit bins, same provider/exchange/product. ` : ''}Sizes use unverified provider units. Minute timestamps label buckets, not guaranteed capture instants. Missing minutes are not filled; distinct same-timestamp books remain separate.`}
    />
  );
}
