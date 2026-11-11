/**
 * Synchronized multi-pane time-series shell: one `main` chart over any number of `study`
 * panes (oscillators, volume, weights, drawdowns), or several mains stacked.
 *
 * A main pane keeps its standalone 16:9 height and each study adds a third of it, so the
 * plots read 3:1 main-to-study, the trading-terminal convention, down to a square frame.
 * Linked rows subtract their fixed label and axis chrome first, so the plots themselves,
 * not the boxes around them, hold that ratio. Linked mode
 * shares one time axis across the panes, sizes one value gutter from the widest label any
 * pane reports, overlays the pane labels on the plots, tracks a single crosshair through
 * the whole stack, and, when panes declare `tooltip`, renders one tooltip for all of them.
 *
 * USAGE:
 *   <MultiPaneTimeSeriesChart panes={[{ id: 'price', label: 'Price', content: <Plot /> }]} />
 *   <MultiPaneTimeSeriesChart
 *     linked
 *     xDomain={domain}
 *     panes={[
 *       { id: 'price', label: 'Price', content: <Plot />, tooltip: priceRows },
 *       { id: 'rsi', label: 'RSI', size: 'study', content: <Plot />, tooltip: rsiRows },
 *       { id: 'volume', label: 'Volume', size: 'study', content: <Plot /> },
 *     ]}
 *   />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  type CSSProperties,
  type ReactNode,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { formatTooltipDate as formatTooltipHeaderDate } from '../charts/timeAxisFormat';
import { type MultiPaneSize, multiPaneAspectRatio, QF_PANE_HEIGHT } from '../core/geometry';
import { containTooltipAtCursor } from '../core/tooltip';
import { useRafState } from '../hooks/useRafState';
import { type ChartTooltipItem, ChartTooltipItems } from './ChartTooltip';
import {
  crosshairOffset,
  DEFAULT_PANE_GUTTER,
  dateAtOffset,
  leftInsetForLabelWidth,
  linkedPaneChrome,
  type MultiPaneGutter,
  type MultiPaneLink,
  MultiPaneLinkProvider,
  panePosition,
} from './MultiPaneContext';
import { TimeSeriesChart } from './TimeSeriesChart';

import './MultiPaneTimeSeriesChart.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

/** One pane's rows in the stack's shared tooltip, resolved at the crosshair time. */
export interface MultiPaneTooltipSection {
  /** Time of the sample the rows describe; the first pane's date heads the tooltip. */
  date: Date;
  items: readonly ChartTooltipItem[];
  detail?: string;
}

export interface MultiPaneTimeSeriesPane {
  id: string;
  label: ReactNode;
  content: ReactNode;
  /** Row height: a full `main` chart (default) or a third-height `study` under it. */
  size?: MultiPaneSize;
  /**
   * Rows this pane adds to the stack's single tooltip at the crosshair time; null when the
   * pane has nothing there. Linked stacks with an `xDomain` only; the panes' own tooltips
   * turn off as soon as any pane declares one.
   */
  tooltip?: (date: Date) => MultiPaneTooltipSection | null;
}

export interface MultiPaneTimeSeriesChartProps {
  title?: string;
  /** Heading element for the chart title; forwarded to ChartFrame (default 3). */
  headingLevel?: 2 | 3 | 4;
  titleAccessory?: ReactNode;
  panes: readonly MultiPaneTimeSeriesPane[];
  className?: string;
  headerRight?: ReactNode;
  legend?: ReactNode;
  collapsibleLegend?: boolean;
  controls?: ReactNode;
  /** Caption rendered in the frame footer, under the panes and controls. */
  footer?: ReactNode;
  /** Share one time axis, aligned gutters, overlaid labels, and a crosshair across panes. */
  linked?: boolean;
  /**
   * Plot insets shared by every linked pane. The left inset defaults to the widest value
   * label the panes report; the right one clears the last tick.
   */
  gutter?: Partial<MultiPaneGutter>;
  /** Time domain every linked pane plots against, so sparse panes stay aligned. */
  xDomain?: readonly [Date, Date];
  /** Header text of the shared tooltip; defaults to the sample's local calendar date. */
  formatTooltipDate?: (date: Date) => string;
}

interface PointerSample {
  x: number;
  y: number;
  width: number;
  height: number;
}

// --------------------------------------------------------------------------- #
// Layout
// --------------------------------------------------------------------------- #

/** Footprint assumed for the shared tooltip until the DOM reports its real size. */
const TOOLTIP_SIZE_GUESS: readonly [number, number] = [180, 96];

/**
 * Grid rows for a stack. Unlinked panes share the height by their sizes. Linked panes
 * first keep their fixed chrome (label inset, axis or edge inset, divider) and share the
 * rest, so their plot heights hold the size ratio exactly.
 */
export function buildMultiPaneRows(
  sizes: readonly (MultiPaneSize | undefined)[],
  { linked = false, controls = false }: { linked?: boolean; controls?: boolean } = {},
): string {
  const heights = sizes.map((size) => QF_PANE_HEIGHT[size ?? 'main']);
  const total = heights.reduce((sum, height) => sum + height, 0);
  const chrome = sizes.map((_, index) => linkedPaneChrome(panePosition(index, sizes.length)));
  const totalChrome = chrome.reduce((sum, height) => sum + height, 0);
  const rows = heights.map((height, index) => {
    if (!linked) return `minmax(0, ${height}fr)`;
    const share = Number((height / total).toFixed(6));
    return `calc(${chrome[index]}px + (100% - ${totalChrome}px) * ${share})`;
  });
  return [...rows, ...(controls ? ['auto'] : [])].join(' ');
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function MultiPaneTimeSeriesChart({
  title,
  headingLevel = 3,
  titleAccessory,
  panes,
  className = '',
  headerRight,
  legend,
  collapsibleLegend = true,
  controls,
  footer,
  linked = false,
  gutter,
  xDomain,
  formatTooltipDate = formatTooltipHeaderDate,
}: MultiPaneTimeSeriesChartProps) {
  const paneCount = panes.length;
  const domainStart = xDomain?.[0].getTime();
  const domainEnd = xDomain?.[1].getTime();
  const domain = useMemo<readonly [Date, Date] | null>(
    () =>
      domainStart != null && domainEnd != null
        ? [new Date(domainStart), new Date(domainEnd)]
        : null,
    [domainEnd, domainStart],
  );

  // Every linked pane reports the width of its widest value label; the stack keeps the
  // maximum so the value axes line up. The callbacks are stable per pane index so a
  // report never re-options the panes through a changed context value.
  const [labelWidths, setLabelWidths] = useState<readonly number[]>([]);
  const requestLeftInsets = useMemo(
    () =>
      Array.from({ length: paneCount }, (_, index) => (width: number) => {
        const next = Number.isFinite(width) ? Math.max(0, width) : 0;
        setLabelWidths((current) => {
          if (current[index] === next) return current;
          const updated = Array.from({ length: paneCount }, (_, i) => current[i] ?? 0);
          updated[index] = next;
          return updated;
        });
      }),
    [paneCount],
  );
  const widestLabel = labelWidths.reduce((widest, width) => Math.max(widest, width), 0);
  const gutterLeft = gutter?.left ?? leftInsetForLabelWidth(widestLabel);
  const gutterRight = gutter?.right ?? DEFAULT_PANE_GUTTER.right;
  const shellTooltip = linked && domain !== null && panes.some((pane) => pane.tooltip);

  // Link values are memoized so crosshair moves re-render the shell without re-optioning
  // every pane's chart through a changed context value.
  const links = useMemo<MultiPaneLink[]>(() => {
    const paneGutter = { left: gutterLeft, right: gutterRight };
    return Array.from({ length: paneCount }, (_, index) => ({
      position: panePosition(index, paneCount),
      gutter: paneGutter,
      xDomain: domain,
      shellTooltip,
      ...(requestLeftInsets[index] ? { requestLeftInset: requestLeftInsets[index] } : {}),
    }));
  }, [domain, gutterLeft, gutterRight, paneCount, requestLeftInsets, shellTooltip]);

  const [pointer, schedulePointer, flushPointer] = useRafState<PointerSample | null>(null);
  const crosshairX =
    pointer === null
      ? null
      : crosshairOffset(pointer.x, pointer.width, { left: gutterLeft, right: gutterRight });
  const tooltipDate =
    shellTooltip && pointer !== null && crosshairX !== null && domain !== null
      ? dateAtOffset(pointer.x, pointer.width, { left: gutterLeft, right: gutterRight }, domain)
      : null;
  const tooltipSections = useMemo(() => {
    if (tooltipDate === null) return [];
    const sections: { id: string; section: MultiPaneTooltipSection }[] = [];
    for (const pane of panes) {
      const section = pane.tooltip?.(tooltipDate);
      if (section) sections.push({ id: pane.id, section });
    }
    return sections;
  }, [panes, tooltipDate]);

  // The tooltip is laid out once at its guessed size, then re-placed with its real one.
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const [tooltipSize, setTooltipSize] = useState<readonly [number, number]>(TOOLTIP_SIZE_GUESS);
  useLayoutEffect(() => {
    const element = tooltipRef.current;
    if (!element) return;
    const width = element.offsetWidth;
    const height = element.offsetHeight;
    if (width > 0 && height > 0 && (width !== tooltipSize[0] || height !== tooltipSize[1])) {
      setTooltipSize([width, height]);
    }
  });
  const tooltipPosition =
    pointer !== null && tooltipSections.length > 0
      ? containTooltipAtCursor([pointer.x, pointer.y], tooltipSize, [pointer.width, pointer.height])
      : null;
  const headSection = tooltipSections[0]?.section;

  const sizes = panes.map((pane) => pane.size);
  const stackStyle: CSSProperties = { gridTemplateRows: buildMultiPaneRows(sizes, { linked }) };
  const layoutStyle: CSSProperties = {
    gridTemplateRows: controls ? 'minmax(0, 1fr) auto' : 'minmax(0, 1fr)',
  };
  // A BrushBar under linked panes inherits the shared gutters, so its track spans the plots.
  const controlsStyle: CSSProperties | undefined = linked
    ? ({
        '--qf-brush-inset-left': `${gutterLeft}px`,
        '--qf-brush-inset-right': `${gutterRight}px`,
      } as CSSProperties)
    : undefined;

  return (
    <TimeSeriesChart
      headingLevel={headingLevel}
      {...(title === undefined ? {} : { title })}
      {...(titleAccessory === undefined ? {} : { titleAccessory })}
      className={`qf-multi-pane-chart-shell ${className}`.trim()}
      {...(headerRight === undefined ? {} : { headerRight })}
      {...(legend === undefined ? {} : { legend })}
      {...(footer === undefined ? {} : { footer })}
      collapsibleLegend={collapsibleLegend}
      aspectRatio={multiPaneAspectRatio(sizes)}
    >
      <div className="qf-multi-pane-chart-layout" style={layoutStyle}>
        <div
          className={linked ? 'qf-multi-pane-chart-stack is-linked' : 'qf-multi-pane-chart-stack'}
          style={stackStyle}
          onPointerMove={
            linked
              ? (event) => {
                  const bounds = event.currentTarget.getBoundingClientRect();
                  schedulePointer({
                    x: event.clientX - bounds.left,
                    y: event.clientY - bounds.top,
                    width: bounds.width,
                    height: bounds.height,
                  });
                }
              : undefined
          }
          onPointerLeave={linked ? () => flushPointer(null) : undefined}
        >
          {panes.map((pane, index) => {
            const section = (
              <section
                className={
                  linked ? 'qf-multi-pane-chart-pane is-linked' : 'qf-multi-pane-chart-pane'
                }
                key={pane.id}
              >
                <div
                  className="qf-multi-pane-chart-pane-label"
                  style={linked ? { left: gutterLeft } : undefined}
                >
                  {pane.label}
                </div>
                <div className="qf-multi-pane-chart-pane-content">{pane.content}</div>
              </section>
            );
            const link = links[index];
            return linked && link ? (
              <MultiPaneLinkProvider key={pane.id} value={link}>
                {section}
              </MultiPaneLinkProvider>
            ) : (
              section
            );
          })}
          {linked && crosshairX != null ? (
            <div
              className="qf-multi-pane-chart-crosshair"
              style={{ left: crosshairX }}
              aria-hidden="true"
            />
          ) : null}
          {tooltipPosition && headSection ? (
            <div
              className="tooltip qf-multi-pane-chart-tooltip"
              style={{
                transform: `translate3d(${tooltipPosition[0]}px, ${tooltipPosition[1]}px, 0)`,
              }}
              ref={tooltipRef}
              role="status"
            >
              <div className="tooltip-date">{formatTooltipDate(headSection.date)}</div>
              {tooltipSections.map(({ id, section }) => (
                <div className="qf-multi-pane-chart-tooltip-section" key={id}>
                  <ChartTooltipItems
                    items={section.items}
                    {...(section.detail === undefined ? {} : { detail: section.detail })}
                  />
                </div>
              ))}
            </div>
          ) : null}
        </div>
        {controls ? (
          <div
            className={
              linked ? 'qf-multi-pane-chart-controls is-linked' : 'qf-multi-pane-chart-controls'
            }
            style={controlsStyle}
          >
            {controls}
          </div>
        ) : null}
      </div>
    </TimeSeriesChart>
  );
}
