/**
 * Collapsible right-hand feature rail for the dataset chart workspace: a shared
 * `Navigator` docked to the workspace's end edge, listing every plottable column
 * grouped by feature family, searchable, with one-click assignment onto the
 * targeted chart cell's left or right axis. Collapses to the navigator strip.
 *
 * USAGE:
 *   <DatasetChartFeatureRail
 *     metrics={bundle.y_columns}
 *     families={bundle.families}
 *     metricFamilies={bundle.y_column_families}
 *     cells={cells}
 *     targetCellId="cell-1"
 *     collapsed={false}
 *     onTargetCellChange={setTarget}
 *     onToggleCollapse={toggle}
 *     onAssign={updateCell}
 *   />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useDeferredValue, useId, useState } from 'react';

import type { DatasetFeatureFamily } from '@/lib/api/catalog';
import { Button, Field, Input, Navigator, SelectControl, Text } from '@/ui';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type DatasetChartAxisSide = 'leftMetric' | 'rightMetric';

export interface DatasetChartFeatureRailCell {
  id: string;
  label: string;
  leftMetric: string | null;
  rightMetric: string | null;
}

export interface DatasetChartFeatureRailGroup {
  id: string;
  label: string;
  metrics: string[];
}

export interface DatasetChartFeatureRailProps {
  metrics: string[];
  families: DatasetFeatureFamily[];
  metricFamilies: Record<string, string>;
  cells: DatasetChartFeatureRailCell[];
  targetCellId: string;
  collapsed: boolean;
  onTargetCellChange: (cellId: string) => void;
  onToggleCollapse: () => void;
  onAssign: (cellId: string, side: DatasetChartAxisSide, metric: string | null) => void;
}

const ALL_FAMILIES = 'all';
const FALLBACK_FAMILY: DatasetFeatureFamily = { id: 'other', label: 'Other', count: 0 };

// --------------------------------------------------------------------------- #
// Pure helpers
// --------------------------------------------------------------------------- #

export function filterMetrics(metrics: string[], query: string): string[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return metrics;
  return metrics.filter((metric) => metric.toLowerCase().includes(needle));
}

/** Group metrics by family, keeping the API's family order and schema order within a family. */
export function groupMetricsByFamily(
  metrics: string[],
  families: DatasetFeatureFamily[],
  metricFamilies: Record<string, string>,
): DatasetChartFeatureRailGroup[] {
  const groups = new Map<string, DatasetChartFeatureRailGroup>();
  for (const family of families) {
    groups.set(family.id, { id: family.id, label: family.label, metrics: [] });
  }
  for (const metric of metrics) {
    const familyId = metricFamilies[metric] ?? FALLBACK_FAMILY.id;
    let group = groups.get(familyId);
    if (!group) {
      group = {
        id: familyId,
        label: familyId === FALLBACK_FAMILY.id ? FALLBACK_FAMILY.label : familyId,
        metrics: [],
      };
      groups.set(familyId, group);
    }
    group.metrics.push(metric);
  }
  return [...groups.values()].filter((group) => group.metrics.length > 0);
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function DatasetChartFeatureRail({
  metrics,
  families,
  metricFamilies,
  cells,
  targetCellId,
  collapsed,
  onTargetCellChange,
  onToggleCollapse,
  onAssign,
}: DatasetChartFeatureRailProps) {
  const controlId = useId();
  const [query, setQuery] = useState('');
  const [family, setFamily] = useState(ALL_FAMILIES);
  const deferredQuery = useDeferredValue(query);

  const target = cells.find((cell) => cell.id === targetCellId) ?? cells[0] ?? null;
  const groups = groupMetricsByFamily(
    filterMetrics(metrics, deferredQuery),
    families,
    metricFamilies,
  ).filter((group) => family === ALL_FAMILIES || group.id === family);

  function toggleAxis(side: DatasetChartAxisSide, metric: string) {
    if (!target) return;
    onAssign(target.id, side, target[side] === metric ? null : metric);
  }

  return (
    <Navigator
      title="Features"
      // Feature names are long and each row also carries the L/R buttons, so this rail runs
      // wider than a section navigator: narrow fits most names, wide fits long ones.
      className="[--section-nav-width-narrow:21rem] [&:not(.is-narrow)]:[--section-nav-width:26rem]"
      side="end"
      collapsedVariant="strip"
      collapsed={collapsed}
      onCollapsedChange={() => onToggleCollapse()}
      collapseOnSelect={false}
      density="compact"
      mono
      listLabel="Chart features"
      empty="No features match"
      headerActions={
        <Text variant="data" tone="muted">
          {metrics.length}
        </Text>
      }
      controls={
        <>
          <Input
            type="search"
            aria-label="Filter chart features"
            placeholder="Filter features"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {families.length > 1 ? (
            <SelectControl
              ariaLabel="Feature block"
              value={family}
              onValueChange={setFamily}
              options={[
                { value: ALL_FAMILIES, label: 'All blocks' },
                ...families.map((item) => ({
                  value: item.id,
                  label: `${item.label} (${item.count})`,
                })),
              ]}
            />
          ) : null}
          {cells.length > 1 && target ? (
            <Field label="Target" htmlFor={`${controlId}-target`} layout="inline">
              <SelectControl
                id={`${controlId}-target`}
                value={target.id}
                onValueChange={onTargetCellChange}
                options={cells.map((cell) => ({ value: cell.id, label: cell.label }))}
              />
            </Field>
          ) : null}
        </>
      }
      groups={groups.map((group) => ({
        id: group.id,
        label: group.label,
        meta: group.metrics.length,
        items: group.metrics.map((metric) => {
          const onLeft = target?.leftMetric === metric;
          const onRight = target?.rightMetric === metric;
          const targetLabel = target?.label ?? 'chart';
          const leftTitle = `${onLeft ? 'Remove from' : 'Plot on'} ${targetLabel} left axis`;
          const rightTitle = `${onRight ? 'Remove from' : 'Plot on'} ${targetLabel} right axis`;
          return {
            id: metric,
            label: metric,
            current: onLeft || onRight,
            pressed: onLeft,
            title: leftTitle,
            onSelect: () => toggleAxis('leftMetric', metric),
            actions: (
              <>
                <Button
                  type="button"
                  variant="nav"
                  aria-pressed={onLeft}
                  aria-label={`${metric} on ${targetLabel} left axis`}
                  title={leftTitle}
                  onClick={() => toggleAxis('leftMetric', metric)}
                >
                  L
                </Button>
                <Button
                  type="button"
                  variant="nav"
                  aria-pressed={onRight}
                  aria-label={`${metric} on ${targetLabel} right axis`}
                  title={rightTitle}
                  onClick={() => toggleAxis('rightMetric', metric)}
                >
                  R
                </Button>
              </>
            ),
          };
        }),
      }))}
    />
  );
}
