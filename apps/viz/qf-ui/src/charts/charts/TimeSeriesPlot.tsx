/**
 * Portable tooltip adapter over the qf-charts line engine.
 *
 * USAGE:
 *   <TimeSeriesPlot data={points} series={[{ id: 's', data: points, color: '…' }]} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useCallback } from 'react';
import { chartTooltipHtml } from '../components/ChartTooltip';
import type { QfInterpolation } from './interpolation';
import { LineChart, type QfAreaGradient, type QfLinePoint, type QfXBand } from './LineChart';
import { findNearestPoint, type MultiSeriesPoint } from './multiSeriesModel';
import { formatTooltipDate } from './timeAxisFormat';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

/** @deprecated use interpolation (`QfInterpolation`). */
export type CurveKind = 'monotone' | 'stepAfter';

export interface TimeSeriesSeries {
  id: string;
  data: MultiSeriesPoint[];
  color: string;
  /** `false` draws the area fill alone with no stroke; drawn lines share one width. */
  showLine?: boolean;
  isBenchmark?: boolean;
  opacity?: number;
  /** @deprecated use interpolation */
  curve?: CurveKind;
  /** How the line joins its points; wins over `curve`. Linear by default. */
  interpolation?: QfInterpolation;
  area?: boolean;
  areaFill?: string | QfAreaGradient;
  /** Fill opacity when it should differ from the stroke opacity. */
  areaOpacity?: number;
  areaBaseline?: 'range' | 'zero';
  defined?: (point: MultiSeriesPoint) => boolean;
  axis?: 'left' | 'right';
}

export interface TimeSeriesPlotProps {
  data: MultiSeriesPoint[];
  series: TimeSeriesSeries[];
  xDomain?: [Date, Date];
  yDomain?: [number, number];
  yRightDomain?: [number, number];
  yScaleType?: 'linear' | 'log';
  ySplitNumber?: number;
  yFormat?: (value: number) => string;
  yRightFormat?: (value: number) => string;
  padding?: { top: number; right: number; bottom: number; left: number };
  thresholdY?: number;
  /** Shaded time intervals behind the series; memoize the array. */
  xBands?: readonly QfXBand[];
  tooltipItems?: (nearest: MultiSeriesPoint) => { label: string; value: string; swatch?: string }[];
  tooltipDetail?: (nearest: MultiSeriesPoint) => string | undefined;
  showXAxis?: boolean;
  showYAxis?: boolean;
  showYAxisLabels?: boolean;
  preservePlotGeometry?: boolean;
  /** Series id kept at full strength while a legend row is hovered. */
  emphasizedSeries?: string | null;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function TimeSeriesPlot({
  data,
  series,
  xDomain,
  yDomain,
  yRightDomain,
  yScaleType,
  ySplitNumber,
  yFormat,
  yRightFormat,
  padding,
  thresholdY,
  xBands,
  tooltipItems,
  tooltipDetail,
  showXAxis,
  showYAxis,
  showYAxisLabels,
  preservePlotGeometry,
  emphasizedSeries = null,
}: TimeSeriesPlotProps) {
  const tooltipHtml = useCallback(
    (date: Date) => {
      const nearest = findNearestPoint(data, date);
      if (!nearest || !tooltipItems) return '';
      const detail = tooltipDetail?.(nearest);
      return chartTooltipHtml({
        date: formatTooltipDate(nearest.date),
        items: tooltipItems(nearest),
        ...(detail ? { detail } : {}),
      });
    },
    [data, tooltipDetail, tooltipItems],
  );

  return (
    <LineChart
      series={series.map((item) => ({
        key: item.id,
        label: item.id,
        points: item.data,
        color: item.color,
        axis: item.axis === 'right' ? ('secondary' as const) : ('primary' as const),
        ...(item.isBenchmark === undefined ? {} : { isBenchmark: item.isBenchmark }),
        ...(item.showLine === undefined ? {} : { showLine: item.showLine }),
        ...(item.opacity === undefined ? {} : { opacity: item.opacity, areaOpacity: item.opacity }),
        ...(item.curve === undefined ? {} : { curve: item.curve }),
        ...(item.interpolation === undefined ? {} : { interpolation: item.interpolation }),
        ...(item.area === undefined ? {} : { area: item.area }),
        ...(item.defined
          ? {
              defined: (point: QfLinePoint) =>
                point.value != null && item.defined?.({ ...point, value: point.value }) === true,
            }
          : {}),
        ...(item.areaFill === undefined ? {} : { areaColor: item.areaFill }),
        ...(item.areaOpacity === undefined ? {} : { areaOpacity: item.areaOpacity }),
        ...(item.areaBaseline === undefined ? {} : { areaBaseline: item.areaBaseline }),
      }))}
      height="100%"
      {...(xDomain === undefined ? {} : { xDomain })}
      {...(yDomain === undefined ? {} : { yDomain })}
      {...(yRightDomain === undefined ? {} : { ySecondaryDomain: yRightDomain })}
      {...(yScaleType === undefined ? {} : { yScaleType })}
      {...(ySplitNumber === undefined ? {} : { ySplitNumber })}
      {...(yFormat === undefined ? {} : { yFormat })}
      {...(yRightFormat === undefined ? {} : { ySecondaryFormat: yRightFormat })}
      {...(padding === undefined ? {} : { padding })}
      {...(thresholdY === undefined ? {} : { thresholdY })}
      {...(xBands === undefined ? {} : { xBands })}
      {...(tooltipItems ? { tooltipHtml } : {})}
      {...(showXAxis === undefined ? {} : { showXAxis })}
      {...(showYAxis === undefined ? {} : { showYAxis })}
      {...(showYAxisLabels === undefined ? {} : { showYAxisLabels })}
      {...(preservePlotGeometry === undefined ? {} : { preservePlotGeometry })}
      emphasizedSeries={emphasizedSeries}
      ariaLabel="Time series chart"
      className="ts-plot-host"
    />
  );
}
