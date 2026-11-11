/**
 * Lineage graph: an ordered history drawn as a subway map. The trunk (the ancestry of
 * `trunkId`) runs as one bold line; every other node hangs off its parent on a side lane,
 * so branches, dead ends and fan-outs read at a glance. Selecting a node highlights its
 * ancestry and dims the rest. Horizontal (default) runs oldest → newest left to right;
 * vertical runs newest first top to bottom with a text row beside each node. A V/H toggle
 * sits top right; pass `orientation` + `onOrientationChange` to control it (e.g. from the URL).
 *
 * USAGE:
 *   import { LineageGraph } from '@quant-factory/qf-ui/charts/lineage';
 *   <LineageGraph
 *     label="Versions"
 *     items={[
 *       { id: 'v000', label: 'v000', tone: 'info', description: 'Baseline' },
 *       { id: 'v001', parentId: 'v000', label: 'v001', tone: 'success', marked: true },
 *     ]}
 *     selectedId="v001"
 *     onSelect={(id) => setSelected(id)}
 *   />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  type CSSProperties,
  type KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { cn } from '../../lib/cn';
import type { Tone } from '../../lib/tone';
import { ChartToggleGroup } from '../components/ChartToggleGroup';

import './LineageGraph.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type LineageGraphOrientation = 'horizontal' | 'vertical';

export interface LineageGraphItem {
  id: string;
  /** Parent id; a missing or unknown parent makes the node a root. */
  parentId?: string | null;
  /** Short node text, e.g. the version name. */
  label: string;
  tone: Tone;
  /** Ring the node, e.g. a version the operator selected as baseline. */
  marked?: boolean;
  /** Row text beside the node in the vertical layout, e.g. the version's question. */
  description?: string;
  /** Accessible name and hover text. */
  title?: string;
}

export interface LineageGraphProps {
  /** Oldest first. */
  items: readonly LineageGraphItem[];
  /** Accessible name for the graph. */
  label: string;
  /** Tip of the trunk; defaults to the last marked item, else the last item. */
  trunkId?: string | null;
  selectedId?: string | null;
  onSelect: (id: string) => void;
  /** Controlled layout; omit to let the built-in V/H toggle own it. */
  orientation?: LineageGraphOrientation;
  /** Uncontrolled starting layout. Default 'horizontal'. */
  defaultOrientation?: LineageGraphOrientation;
  onOrientationChange?: (orientation: LineageGraphOrientation) => void;
  className?: string;
}

interface PlacedNode {
  item: LineageGraphItem;
  index: number;
  lane: number;
  parentIndex: number | null;
  trunk: boolean;
}

// --------------------------------------------------------------------------- #
// Layout
// --------------------------------------------------------------------------- #

const STEP = 24; // px between consecutive nodes along the time axis (and vertical row height)
const LANE = 20; // px between lanes
const PAD = 12; // px around the drawing
const LABEL_ROOM = 16; // px above the trunk for marked labels in the horizontal layout
const LABEL_SIDE = 14; // px at each end so the first and last labels are not clipped
const RADIUS = 6; // px elbow radius where a branch leaves its parent

/** Trunk on lane 0; each branch takes the first lane free over its span, first children continue in their parent's lane. */
function layoutLineage(
  items: readonly LineageGraphItem[],
  trunkId: string | null | undefined,
): PlacedNode[] {
  const index = new Map(items.map((item, i) => [item.id, i]));
  const parentOf = (item: LineageGraphItem) =>
    item.parentId != null && item.parentId !== item.id && index.has(item.parentId)
      ? item.parentId
      : null;
  const children = new Map<string, string[]>();
  for (const item of items) {
    const parent = parentOf(item);
    if (parent) children.set(parent, [...(children.get(parent) ?? []), item.id]);
  }
  const byId = new Map(items.map((item) => [item.id, item]));

  const trunk = new Set<string>();
  let tip: LineageGraphItem | undefined =
    (trunkId ? byId.get(trunkId) : undefined) ??
    [...items].reverse().find((item) => item.marked) ??
    items.at(-1);
  while (tip && !trunk.has(tip.id)) {
    trunk.add(tip.id);
    const parent = parentOf(tip);
    tip = parent ? byId.get(parent) : undefined;
  }

  const lane = new Map<string, number>();
  for (const id of trunk) lane.set(id, 0);
  const spans: Array<Array<[number, number]>> = [];
  const branchChildren = (id: string) =>
    (children.get(id) ?? []).filter((child) => !trunk.has(child));
  const lastIndex = (id: string, seen = new Set<string>()): number => {
    seen.add(id);
    let last = index.get(id) ?? 0;
    for (const child of branchChildren(id))
      if (!seen.has(child)) last = Math.max(last, lastIndex(child, seen));
    return last;
  };
  const place = (id: string, at: number) => {
    lane.set(id, at);
    branchChildren(id).forEach((child, i) => {
      if (lane.has(child)) return;
      if (i === 0) place(child, at);
      else branch(child);
    });
  };
  const branch = (id: string) => {
    const item = byId.get(id);
    const parent = item ? parentOf(item) : null;
    const start = index.get(parent ?? id) ?? 0;
    const end = lastIndex(id);
    let at = 1;
    while ((spans[at] ?? []).some(([from, to]) => start < to && from < end)) at += 1;
    spans[at] = [...(spans[at] ?? []), [start, end]];
    place(id, at);
  };
  for (const item of items) {
    const parent = parentOf(item);
    if (!lane.has(item.id) && (parent === null || lane.has(parent))) branch(item.id);
  }
  for (const item of items) if (!lane.has(item.id)) branch(item.id); // cycles

  return items.map((item, i) => {
    const parent = parentOf(item);
    return {
      item,
      index: i,
      lane: lane.get(item.id) ?? 0,
      parentIndex: parent ? (index.get(parent) ?? null) : null,
      trunk: trunk.has(item.id),
    };
  });
}

function ancestry(
  nodes: readonly PlacedNode[],
  selectedId: string | null | undefined,
): Set<string> {
  const path = new Set<string>();
  let node = nodes.find((n) => n.item.id === selectedId);
  while (node && !path.has(node.item.id)) {
    path.add(node.item.id);
    node = node.parentIndex === null ? undefined : nodes[node.parentIndex];
  }
  return path;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function LineageGraph({
  items,
  label,
  trunkId,
  selectedId = null,
  onSelect,
  orientation: orientationProp,
  defaultOrientation = 'horizontal',
  onOrientationChange,
  className,
}: LineageGraphProps) {
  const [ownOrientation, setOwnOrientation] = useState(defaultOrientation);
  const orientation = orientationProp ?? ownOrientation;
  const setOrientation = (next: LineageGraphOrientation) => {
    setOwnOrientation(next);
    onOrientationChange?.(next);
  };
  const nodes = useMemo(() => layoutLineage(items, trunkId), [items, trunkId]);
  const path = useMemo(() => ancestry(nodes, selectedId), [nodes, selectedId]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const vertical = orientation === 'vertical';
  const count = nodes.length;
  const lanes = Math.max(0, ...nodes.map((n) => n.lane)) + 1;

  // Time and lane coordinates, then mapped to x/y per orientation.
  const time = (i: number) =>
    vertical ? (count - 1 - i) * STEP + STEP / 2 : PAD + LABEL_SIDE + i * STEP;
  const across = (l: number) => PAD + l * LANE + (vertical ? 0 : LABEL_ROOM);
  const xy = (t: number, a: number) => (vertical ? `${a} ${t}` : `${t} ${a}`);
  const graphSize = 2 * PAD + (lanes - 1) * LANE;
  const width = vertical ? graphSize : 2 * (PAD + LABEL_SIDE) + (count - 1) * STEP;
  const height = vertical ? count * STEP : graphSize + LABEL_ROOM;

  // Keep the selected node in view inside the scroller only (never scrolls the page).
  useEffect(() => {
    const scroller = scrollRef.current;
    const target = scroller?.querySelector<HTMLElement | SVGElement>(
      `[data-node-id="${CSS.escape(selectedId ?? '')}"]`,
    );
    if (!scroller || !target) return;
    const box = scroller.getBoundingClientRect();
    const node = target.getBoundingClientRect();
    if (vertical && (node.top < box.top || node.bottom > box.bottom))
      scroller.scrollTop += node.top - box.top - box.height / 2;
    if (!vertical && (node.left < box.left || node.right > box.right))
      scroller.scrollLeft += node.left - box.left - box.width / 2;
  }, [selectedId, vertical]);

  const onKey = (event: KeyboardEvent, id: string) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    onSelect(id);
  };

  const graph = (
    <svg
      className="qf-lineage-graph-svg"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden={vertical || undefined}
      role={vertical ? undefined : 'group'}
      aria-label={vertical ? undefined : label}
    >
      {nodes.map((node) => {
        if (node.parentIndex === null) return null;
        const parent = nodes[node.parentIndex];
        if (!parent) return null;
        const [pt, pa, ct, ca] = [
          time(parent.index),
          across(parent.lane),
          time(node.index),
          across(node.lane),
        ];
        const sa = Math.sign(ca - pa);
        const st = Math.sign(ct - pt);
        const d =
          pa === ca
            ? `M${xy(pt, pa)}L${xy(ct, ca)}`
            : `M${xy(pt, pa)}L${xy(pt, ca - sa * RADIUS)}Q${xy(pt, ca)} ${xy(pt + st * RADIUS, ca)}L${xy(ct, ca)}`;
        return (
          <path
            key={`edge-${node.item.id}`}
            className={cn(
              'qf-lineage-edge',
              node.trunk && parent.trunk && 'is-trunk',
              path.size > 0 && !path.has(node.item.id) && 'is-off',
            )}
            d={d}
          />
        );
      })}
      {nodes.map((node) => {
        const [x, y] = vertical
          ? [across(node.lane), time(node.index)]
          : [time(node.index), across(node.lane)];
        const selected = node.item.id === selectedId;
        return (
          <g
            key={node.item.id}
            className={cn(
              'qf-lineage-node',
              `tone-${node.item.tone}`,
              node.trunk && 'is-trunk',
              selected && 'is-selected',
              path.size > 0 && !path.has(node.item.id) && 'is-off',
            )}
            data-node-id={vertical ? undefined : node.item.id}
            {...(vertical
              ? {}
              : {
                  role: 'button',
                  tabIndex: 0,
                  'aria-pressed': selected,
                  'aria-label': node.item.title ?? node.item.label,
                  onKeyDown: (event: KeyboardEvent) => onKey(event, node.item.id),
                })}
            onClick={() => onSelect(node.item.id)}
          >
            <title>{node.item.title ?? node.item.label}</title>
            {node.item.marked ? <circle className="qf-lineage-mark" cx={x} cy={y} r={9} /> : null}
            <circle className="qf-lineage-dot" cx={x} cy={y} r={node.trunk ? 5 : 4} />
            {!vertical && (node.item.marked || selected) ? (
              <text
                className="qf-lineage-label"
                x={x}
                y={node.lane === 0 ? y - 13 : y + 19}
                textAnchor="middle"
              >
                {node.item.label}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );

  return (
    <div className={cn('qf-lineage', className)}>
      <div className="qf-lineage-toolbar">
        <ChartToggleGroup
          ariaLabel="Graph layout"
          options={[
            { value: 'vertical', label: 'V', ariaLabel: 'Vertical' },
            { value: 'horizontal', label: 'H', ariaLabel: 'Horizontal' },
          ]}
          value={orientation}
          onChange={setOrientation}
        />
      </div>
      <div
        ref={scrollRef}
        className={cn('qf-lineage-graph', vertical ? 'is-vertical' : 'is-horizontal')}
        style={{ '--lineage-step': `${STEP}px` } as CSSProperties}
      >
        {vertical ? (
          <div className="qf-lineage-columns">
            {graph}
            <ol className="qf-lineage-rows" aria-label={label}>
              {[...nodes].reverse().map((node) => {
                const selected = node.item.id === selectedId;
                return (
                  <li key={node.item.id}>
                    <button
                      type="button"
                      className={cn(
                        'qf-lineage-row',
                        selected && 'is-selected',
                        path.size > 0 && !path.has(node.item.id) && 'is-off',
                      )}
                      data-node-id={node.item.id}
                      aria-pressed={selected}
                      title={node.item.title}
                      onClick={() => onSelect(node.item.id)}
                    >
                      <span className="qf-lineage-row-label">
                        {node.item.label}
                        {node.item.marked ? ' ★' : ''}
                      </span>
                      <span className="qf-lineage-row-text">{node.item.description}</span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </div>
        ) : (
          graph
        )}
      </div>
    </div>
  );
}
