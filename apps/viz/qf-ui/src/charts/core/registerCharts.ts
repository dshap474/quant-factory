/**
 * Idempotent registration for the qf-charts ECharts runtime.
 *
 * USAGE:
 *   registerCharts();
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  BarChart,
  CandlestickChart,
  CustomChart,
  HeatmapChart,
  LineChart,
  ScatterChart,
  TreemapChart,
} from 'echarts/charts';
import {
  AriaComponent,
  DataZoomComponent,
  DataZoomInsideComponent,
  DataZoomSliderComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';

// --------------------------------------------------------------------------- #
// Registration
// --------------------------------------------------------------------------- #

let registered = false;

export function registerCharts(): void {
  if (registered) return;
  echarts.use([
    BarChart,
    CandlestickChart,
    CustomChart,
    HeatmapChart,
    LineChart,
    ScatterChart,
    TreemapChart,
    AriaComponent,
    DataZoomComponent,
    DataZoomInsideComponent,
    DataZoomSliderComponent,
    GridComponent,
    LegendComponent,
    MarkAreaComponent,
    MarkLineComponent,
    MarkPointComponent,
    TitleComponent,
    TooltipComponent,
    VisualMapComponent,
    CanvasRenderer,
  ]);
  registered = true;
}

export function isChartRuntimeRegistered(): boolean {
  return registered;
}
