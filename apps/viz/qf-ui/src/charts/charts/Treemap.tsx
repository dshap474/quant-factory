/**
 * Nested area map: each rectangle's area is its value, children tile inside their parent.
 *
 * USAGE:
 *   <Treemap
 *     ariaLabel="Lake size"
 *     nodes={[{ id: 'raw', name: 'raw', value: 53, color: chartColor(2), children: [...] }]}
 *     formatValue={(value) => `${value.toFixed(1)} GB`}
 *   />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useMemo } from 'react';

import { QF_CHART_ASPECT_RATIO, QfChart, type QfChartOption } from '../core/QfChart';
import { qfEChartsTooltip } from '../core/tooltip';
import { useChartTheme } from '../hooks/useChartTheme';
import { resolveChartFont, resolveCssColor } from '../theme/tokens';
import { escapeHtml } from '../utils/escapeHtml';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface TreemapNode {
  id: string;
  name: string;
  /** Area weight. A parent's area is the sum of its children's values. */
  value: number;
  /** CSS colour; children without one inherit their parent's. Labels are light, so pass a muted fill. */
  color?: string | undefined;
  /** Extra tooltip line under the path and formatted value. */
  detail?: string | undefined;
  children?: readonly TreemapNode[] | undefined;
}

export interface TreemapProps {
  nodes: readonly TreemapNode[];
  ariaLabel: string;
  formatValue?: ((value: number) => string) | undefined;
  height?: number | string | undefined;
  className?: string | undefined;
  onNodeClick?: ((node: TreemapNode) => void) | undefined;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

interface TreemapDatum {
  id: string;
  name: string;
  value: number;
  node: TreemapNode;
  itemStyle?: { color: string };
  children?: TreemapDatum[];
}

function toDatum(node: TreemapNode): TreemapDatum {
  const datum: TreemapDatum = { id: node.id, name: node.name, value: node.value, node };
  if (node.color) datum.itemStyle = { color: resolveCssColor(node.color) };
  if (node.children?.length) datum.children = node.children.map(toDatum);
  return datum;
}

function pickNode(params: unknown): TreemapNode | null {
  if (!params || typeof params !== 'object') return null;
  const data = (params as { data?: { node?: TreemapNode } }).data;
  return data?.node ?? null;
}

function treePath(params: unknown): string {
  const info = (params as { treePathInfo?: { name: string }[] }).treePathInfo ?? [];
  return info
    .slice(1)
    .map((step) => step.name)
    .join(' / ');
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Treemap({
  nodes,
  ariaLabel,
  formatValue = (value) => value.toLocaleString('en-US'),
  height,
  className,
  onNodeClick,
}: TreemapProps) {
  const theme = useChartTheme();
  const option = useMemo<QfChartOption>(() => {
    const font = resolveChartFont();
    const upperLabel = {
      show: true,
      height: 22,
      color: theme.tooltipText,
      fontFamily: font,
      fontSize: 11,
      formatter: (params: unknown) => {
        const { name, value } = params as { name: string; value: number };
        return `${name}  ${formatValue(value)}`;
      },
    };
    return {
      animation: false,
      backgroundColor: 'transparent',
      tooltip: {
        ...qfEChartsTooltip(theme),
        formatter: (params: unknown) => {
          const node = pickNode(params);
          if (!node) return '';
          const lines = [treePath(params), formatValue(node.value), node.detail ?? ''];
          return lines
            .filter(Boolean)
            .map((line) => escapeHtml(line))
            .join('<br/>');
        },
      },
      series: [
        {
          type: 'treemap',
          data: nodes.map(toDatum),
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          roam: false,
          nodeClick: false,
          breadcrumb: { show: false },
          // Squarified tiles below this share of the parent area are not drawn.
          visibleMin: 1,
          label: {
            show: true,
            color: theme.tooltipText,
            fontFamily: font,
            fontSize: 11,
            overflow: 'truncate',
            formatter: (params: unknown) => {
              const { name, value } = params as { name: string; value: number };
              return `${name}\n${formatValue(value)}`;
            },
          },
          itemStyle: { borderColor: theme.background, gapWidth: 1 },
          levels: [
            { itemStyle: { borderColor: theme.background, borderWidth: 0, gapWidth: 4 } },
            {
              itemStyle: { borderColor: theme.background, borderWidth: 2, gapWidth: 2 },
              upperLabel,
            },
            {
              itemStyle: { borderColor: theme.background, borderWidth: 2, gapWidth: 1 },
              upperLabel,
            },
            { itemStyle: { borderColor: theme.background, borderWidth: 1, gapWidth: 1 } },
          ],
        },
      ],
      aria: { enabled: true, decal: { show: false } },
    };
  }, [formatValue, nodes, theme]);

  const chart = (
    <QfChart
      option={option}
      ariaLabel={ariaLabel}
      height={height ?? '100%'}
      className={className}
      interactive={Boolean(onNodeClick)}
      onClick={(params) => {
        const node = pickNode(params);
        if (node) onNodeClick?.(node);
      }}
    />
  );
  if (height != null) return chart;
  return <div style={{ aspectRatio: `${QF_CHART_ASPECT_RATIO} / 1` }}>{chart}</div>;
}
