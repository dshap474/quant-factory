/**
 * Responsive chart shell with package-owned header and collapsible legend rail.
 *
 * Single charts keep the 16:9 frame; multi-pane stacks pass the package's stack ratio so
 * every pane stays plot height.
 *
 * USAGE:
 *   <TimeSeriesChart title="Equity" legend={<Legend />}>…</TimeSeriesChart>
 *   <TimeSeriesChart aspectRatio={multiPaneAspectRatio(['main', 'study'])}>…</TimeSeriesChart>
 *   <TimeSeriesChart controls={<BrushBar … />}>{plot}</TimeSeriesChart>
 *
 * A collapsible legend's toggle is pinned to the chart body's top-right corner: on the
 * legend's first row while it is open, floating over the plot once collapsed, so it never
 * moves. Collapsing removes the rail so the plot takes the full width.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { type CSSProperties, type ReactNode, useState } from 'react';

import { QF_CHART_ASPECT_RATIO } from '../core/geometry';
import { ChartFrame } from './ChartFrame';
import { LegendCollapseButton } from './LegendCollapseButton';

import './TimeSeriesChart.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface TimeSeriesChartProps {
  title?: string;
  /** Heading element for the chart title; forwarded to ChartFrame (default 3). */
  headingLevel?: 2 | 3 | 4;
  titleAccessory?: ReactNode;
  className?: string;
  children: ReactNode;
  headerRight?: ReactNode;
  legend?: ReactNode;
  collapsibleLegend?: boolean;
  footer?: ReactNode;
  /** Controls stacked under the plot (e.g. BrushBar); the package owns the stack geometry. */
  controls?: ReactNode;
  /** Frame width over height; package geometry only, never a page-local override. */
  aspectRatio?: number;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function TimeSeriesChart({
  title,
  headingLevel = 3,
  titleAccessory,
  className = '',
  children,
  headerRight,
  legend,
  collapsibleLegend = true,
  footer,
  controls,
  aspectRatio = QF_CHART_ASPECT_RATIO,
}: TimeSeriesChartProps) {
  const [legendCollapsed, setLegendCollapsed] = useState(false);
  const canCollapse = Boolean(legend) && collapsibleLegend;
  const showLegendRail = Boolean(legend) && !(canCollapse && legendCollapsed);
  const legendToggle = canCollapse ? (
    <LegendCollapseButton
      inline
      className="is-corner"
      collapsed={legendCollapsed}
      onToggle={() => setLegendCollapsed((value) => !value)}
    />
  ) : null;
  return (
    <div
      className={`chart-container-shell ${className}`.trim()}
      style={{ '--qf-chart-aspect': `${aspectRatio} / 1` } as CSSProperties}
    >
      <ChartFrame
        headingLevel={headingLevel}
        title={title ? <span className="chart-title">{title}</span> : undefined}
        titleAccessory={titleAccessory}
        actions={headerRight ? <div className="header-right">{headerRight}</div> : undefined}
        footer={footer}
        className="chart-container"
        bodyClassName="chart-panel-body"
      >
        <div className="chart-body" data-legend-collapsed={canCollapse && legendCollapsed}>
          <div className="chart-wrapper">
            {controls ? (
              <div className="chart-stack">
                <div className="chart-stack-main">{children}</div>
                {controls}
              </div>
            ) : (
              children
            )}
          </div>
          {showLegendRail ? (
            <aside className="chart-legend">
              <div className="legend-content">{legend}</div>
            </aside>
          ) : null}
          {legendToggle}
        </div>
      </ChartFrame>
    </div>
  );
}
