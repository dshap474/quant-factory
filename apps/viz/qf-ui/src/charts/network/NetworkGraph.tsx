/**
 * Network graph: nodes and undirected links laid out by a deterministic force simulation
 * (same input, same picture), drawn as SVG. Primary nodes are toned circles, secondary nodes
 * small diamonds; both grow with `weight`. A `series` colours a node from the categorical
 * palette instead of its tone. Hovering or selecting a node focuses it: its neighbors stay lit
 * and, for a primary node with `peers` on, so do its peers (primary nodes that share a
 * neighbor); everything else dims and the focus's links paint on top. Marks and type keep their
 * pixel size at any width: the layout is fitted into the measured drawing, not scaled with it.
 * The focused node and `labeled` nodes carry labels, and so does a focus set of up to ten.
 * A `legend` sits in a rail on the right that collapses so the drawing takes the full width.
 *
 * USAGE:
 *   import { NetworkGraph } from '@quant-factory/qf-ui/charts/network';
 *   <NetworkGraph
 *     label="Design space"
 *     nodes={[
 *       { id: 'lookback', label: 'Lookback', tone: 'success' },
 *       { id: 'v002', label: 'v002', kind: 'secondary', weight: 2, labeled: true },
 *     ]}
 *     links={[{ source: 'lookback', target: 'v002' }]}
 *     selectedId={selected}
 *     onSelect={setSelected}   // receives null when the selected node is clicked again or Escape is pressed
 *   />
 *   <NetworkGraph label="Wiki" nodes={[{ id, label, weight: degree, series: 3 }]} links={links}
 *     peers={false} height="100%" onSelect={open} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  type CSSProperties,
  type KeyboardEvent,
  type RefObject,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { cn } from '../../lib/cn';
import type { Tone } from '../../lib/tone';
import { LegendCollapseButton } from '../components/LegendCollapseButton';

import './NetworkGraph.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type NetworkGraphNodeKind = 'primary' | 'secondary';

export interface NetworkGraphNode {
  id: string;
  label: string;
  /** Default 'primary'. */
  kind?: NetworkGraphNodeKind;
  /** Default 'neutral' for primary nodes, 'info' for secondary nodes. */
  tone?: Tone;
  /** Grows the node's mark, e.g. how many nodes it links. Default 1. */
  weight?: number;
  /** Categorical palette slot (1-20); overrides the tone, e.g. one colour per group. */
  series?: number;
  /** Always show the label, not only when focused or hovered. */
  labeled?: boolean;
  /** Accessible name and hover text; defaults to the label. */
  title?: string;
}

export interface NetworkGraphLink {
  source: string;
  target: string;
}

export interface NetworkGraphLegendItem {
  label: string;
  /** Palette slot the swatch shows; omitted for the secondary (diamond) mark. */
  series?: number;
  /** Swatch tone when there is no `series`; match the nodes it names. */
  tone?: Tone;
}

export interface NetworkGraphProps {
  nodes: readonly NetworkGraphNode[];
  links: readonly NetworkGraphLink[];
  /** Accessible name for the graph. */
  label: string;
  selectedId?: string | null;
  /** Called with a node id, or null when the selected node is clicked again or Escape is pressed. */
  onSelect: (id: string | null) => void;
  /** Focus also lights primary nodes that share a neighbor. Default true. */
  peers?: boolean;
  /** CSS height of the drawing. Default 34rem. */
  height?: string;
  /** Key in a collapsible right rail: a swatch per palette slot (`series`), or the secondary diamond. */
  legend?: readonly NetworkGraphLegendItem[];
  className?: string;
}

interface Point {
  x: number;
  y: number;
}

interface Size {
  width: number;
  height: number;
}

// --------------------------------------------------------------------------- #
// Layout
// --------------------------------------------------------------------------- #

const ITERATIONS = 300;
const LINK_LENGTH = 30;
const MAX_REACH = 120; // px beyond which nodes stop repelling, so unlinked nodes do not drift off
const GRAVITY = 0.004; // pull toward the center
const FIT_PAD = 28; // px kept clear around the marks
const MAX_SCALE = 4; // a small graph spreads out at most this far
const MAX_FOCUS_LABELS = 10; // a focus set this small names every node in it
const LABEL_GAP = 6; // px between a mark and its label
const PRIMARY_RADIUS = 5;
// SVG has no <fieldset> or <button>: these roles (with tabIndex and Enter/Space on nodes) stand in.
const GROUP = { role: 'group' } as const;
const button = (pressed: boolean) => ({ role: 'button', 'aria-pressed': pressed }) as const;

function diamondSize(weight: number): number {
  return 7 + Math.min(weight, 8) * 0.9;
}

/** Weight 1 keeps the base circle; heavier nodes grow with the root of their weight, capped. */
function circleRadius(weight: number): number {
  return PRIMARY_RADIUS + Math.min(Math.sqrt(Math.max(weight, 1)) - 1, 4) * 1.5;
}

/** Force layout: short-range repulsion, degree-scaled spring links and a pull to the center; seeded on a sunflower spiral. */
function layoutNetwork(
  nodes: readonly NetworkGraphNode[],
  links: readonly NetworkGraphLink[],
): Point[] {
  const count = nodes.length;
  const index = new Map(nodes.map((node, i) => [node.id, i]));
  const pairs = links.flatMap((link) => {
    const a = index.get(link.source);
    const b = index.get(link.target);
    return a === undefined || b === undefined || a === b ? [] : [[a, b] as const];
  });
  const charge = nodes.map((node) => (node.kind === 'secondary' ? 40 : 90));
  // A spring pulls less on a well-linked node (d3's link strength), so hubs stay stable.
  const degree = nodes.map(() => 0);
  for (const [a, b] of pairs) {
    degree[a] = (degree[a] as number) + 1;
    degree[b] = (degree[b] as number) + 1;
  }
  const pos = nodes.map((_, i) => {
    const r = 10 * Math.sqrt(i + 0.5);
    const angle = i * 2.399963229728653; // golden angle
    return { x: r * Math.cos(angle), y: r * Math.sin(angle) };
  });
  const vel = nodes.map(() => ({ x: 0, y: 0 }));

  for (let step = 0; step < ITERATIONS; step += 1) {
    const alpha = 1 - step / ITERATIONS;
    for (let i = 0; i < count; i += 1) {
      const a = pos[i] as Point;
      for (let j = i + 1; j < count; j += 1) {
        const b = pos[j] as Point;
        const dx = a.x - b.x || 0.01;
        const dy = a.y - b.y || 0.01;
        const d2 = Math.max(dx * dx + dy * dy, 25);
        if (d2 > MAX_REACH * MAX_REACH) continue;
        const f = (alpha * Math.sqrt((charge[i] as number) * (charge[j] as number))) / d2;
        (vel[i] as Point).x += dx * f;
        (vel[i] as Point).y += dy * f;
        (vel[j] as Point).x -= dx * f;
        (vel[j] as Point).y -= dy * f;
      }
    }
    for (const [i, j] of pairs) {
      const a = pos[i] as Point;
      const b = pos[j] as Point;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const f =
        (alpha * 0.3 * (d - LINK_LENGTH)) / d / Math.min(degree[i] as number, degree[j] as number);
      (vel[i] as Point).x += dx * f;
      (vel[i] as Point).y += dy * f;
      (vel[j] as Point).x -= dx * f;
      (vel[j] as Point).y -= dy * f;
    }
    for (let i = 0; i < count; i += 1) {
      const p = pos[i] as Point;
      const v = vel[i] as Point;
      v.x = (v.x - p.x * GRAVITY) * 0.6;
      v.y = (v.y - p.y * GRAVITY) * 0.6;
      p.x += v.x;
      p.y += v.y;
    }
  }
  return pos;
}

/** Each node's neighbors, built once per link set. */
function adjacency(links: readonly NetworkGraphLink[]): Map<string, string[]> {
  const neighbors = new Map<string, string[]>();
  for (const { source, target } of links) {
    const a = neighbors.get(source);
    if (a) a.push(target);
    else neighbors.set(source, [target]);
    const b = neighbors.get(target);
    if (b) b.push(source);
    else neighbors.set(target, [source]);
  }
  return neighbors;
}

/** The focused node, its neighbors and, for a primary node with `peers`, primary nodes sharing a neighbor. */
function focusSet(
  kinds: ReadonlyMap<string, NetworkGraphNodeKind>,
  neighbors: ReadonlyMap<string, readonly string[]>,
  focusId: string | null,
  peers: boolean,
): Set<string> {
  const lit = new Set<string>();
  const kind = focusId === null ? undefined : kinds.get(focusId);
  if (focusId === null || !kind) return lit;
  lit.add(focusId);
  for (const near of neighbors.get(focusId) ?? []) {
    lit.add(near);
    if (!peers || kind !== 'primary') continue;
    for (const peer of neighbors.get(near) ?? []) if (kinds.get(peer) === 'primary') lit.add(peer);
  }
  return lit;
}

/** Fit the layout into the drawing at a 1:1 pixel scale, centered, so marks and type keep their size. */
function fitToBox(points: readonly Point[], box: Size): Point[] {
  if (points.length === 0) return [];
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const spanX = Math.max(...xs) - minX || 1;
  const spanY = Math.max(...ys) - minY || 1;
  const scale = Math.min(
    (box.width - 2 * FIT_PAD) / spanX,
    (box.height - 2 * FIT_PAD) / spanY,
    MAX_SCALE,
  );
  const offsetX = (box.width - spanX * scale) / 2;
  const offsetY = (box.height - spanY * scale) / 2;
  return points.map((p) => ({
    x: offsetX + (p.x - minX) * scale,
    y: offsetY + (p.y - minY) * scale,
  }));
}

/** The drawing's rendered pixel size, tracked through resizes. */
function useBoxSize(ref: RefObject<Element | null>): Size | null {
  const [size, setSize] = useState<Size | null>(null);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => {
      const { width, height } = element.getBoundingClientRect();
      setSize((previous) =>
        previous && previous.width === width && previous.height === height
          ? previous
          : { width, height },
      );
    };
    measure();
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : undefined;
    observer?.observe(element);
    return () => observer?.disconnect();
  }, [ref]);
  return size;
}

function toneStyle(series: number | undefined): CSSProperties | undefined {
  return series === undefined
    ? undefined
    : ({ '--node-tone': `var(--qf-chart-${series})` } as CSSProperties);
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function NetworkGraph({
  nodes,
  links,
  label,
  selectedId = null,
  onSelect,
  peers = true,
  height,
  legend,
  className,
}: NetworkGraphProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const box = useBoxSize(svgRef);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [legendOpen, setLegendOpen] = useState(true);
  const focusId = hoverId ?? selectedId;

  const layout = useMemo(() => layoutNetwork(nodes, links), [nodes, links]);
  const points = useMemo(() => (box ? fitToBox(layout, box) : []), [layout, box]);
  const kinds = useMemo(
    () => new Map(nodes.map((node) => [node.id, node.kind ?? 'primary'] as const)),
    [nodes],
  );
  const neighbors = useMemo(() => adjacency(links), [links]);
  const lit = useMemo(
    () => focusSet(kinds, neighbors, focusId, peers),
    [kinds, neighbors, focusId, peers],
  );
  const at = useMemo(
    () => new Map(nodes.map((node, i) => [node.id, points[i]] as const)),
    [nodes, points],
  );
  const focused = lit.size > 0;
  // A small focus set reads with every label; a hub's would pile up, so it names only itself.
  const labelLit = lit.size <= MAX_FOCUS_LABELS;

  const onKey = (event: KeyboardEvent, id: string) => {
    if (event.key === 'Escape') onSelect(null);
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    onSelect(id === selectedId ? null : id);
  };

  // Lit links paint last, so the focus is never hidden behind the rest. Nodes keep their
  // order: moving one under the pointer between press and release would drop the click.
  const linkOrder = focused
    ? [...links].sort(
        (a, b) =>
          Number(a.source === focusId || a.target === focusId) -
          Number(b.source === focusId || b.target === focusId),
      )
    : links;
  const labeled = nodes.filter(
    (node) =>
      node.labeled ||
      node.id === focusId ||
      node.id === selectedId ||
      (labelLit && lit.has(node.id)),
  );

  return (
    <div
      className={cn('qf-network', className)}
      data-legend={legend?.length ? (legendOpen ? 'open' : 'closed') : undefined}
    >
      <svg
        ref={svgRef}
        className="qf-network-svg"
        viewBox={box ? `0 0 ${box.width} ${box.height}` : undefined}
        style={height ? { height } : undefined}
        {...GROUP}
        aria-label={label}
      >
        {box ? (
          <>
            <g className="qf-network-links">
              {linkOrder.map((link) => {
                const a = at.get(link.source);
                const b = at.get(link.target);
                if (!a || !b) return null;
                const on = link.source === focusId || link.target === focusId;
                return (
                  <line
                    key={`${link.source}\n${link.target}`}
                    className={cn('qf-network-link', on && 'is-on', focused && !on && 'is-off')}
                    x1={a.x}
                    y1={a.y}
                    x2={b.x}
                    y2={b.y}
                  />
                );
              })}
            </g>
            <g className="qf-network-nodes">
              {nodes.map((node) => {
                const p = at.get(node.id);
                if (!p) return null;
                const secondary = node.kind === 'secondary';
                const selected = node.id === selectedId;
                const size = diamondSize(node.weight ?? 1);
                return (
                  <g
                    key={node.id}
                    className={cn(
                      'qf-network-node',
                      `tone-${node.tone ?? (secondary ? 'info' : 'neutral')}`,
                      secondary && 'is-secondary',
                      selected && 'is-selected',
                      focused && !lit.has(node.id) && 'is-off',
                    )}
                    transform={`translate(${p.x} ${p.y})`}
                    style={toneStyle(node.series)}
                    {...button(selected)}
                    tabIndex={0}
                    aria-label={node.title ?? node.label}
                    onKeyDown={(event) => onKey(event, node.id)}
                    onClick={() => onSelect(selected ? null : node.id)}
                    onPointerEnter={() => setHoverId(node.id)}
                    onPointerLeave={() => setHoverId(null)}
                    onFocus={() => setHoverId(node.id)}
                    onBlur={() => setHoverId(null)}
                  >
                    {secondary ? (
                      <rect
                        className="qf-network-mark"
                        x={-size / 2}
                        y={-size / 2}
                        width={size}
                        height={size}
                        transform="rotate(45)"
                      />
                    ) : (
                      <circle className="qf-network-mark" r={circleRadius(node.weight ?? 1)} />
                    )}
                  </g>
                );
              })}
            </g>
            <g className="qf-network-labels">
              {labeled.map((node) => {
                const p = at.get(node.id);
                if (!p) return null;
                const reach =
                  node.kind === 'secondary'
                    ? diamondSize(node.weight ?? 1) / 2
                    : circleRadius(node.weight ?? 1);
                // Labels on the right third of the drawing read leftward, so they stay inside it.
                const flip = p.x > box.width * (2 / 3);
                return (
                  <text
                    key={node.id}
                    className={cn(
                      'qf-network-label',
                      (node.id === focusId || node.id === selectedId) && 'is-focus',
                    )}
                    x={p.x + (flip ? -(reach + LABEL_GAP) : reach + LABEL_GAP)}
                    y={p.y}
                    textAnchor={flip ? 'end' : 'start'}
                    dominantBaseline="central"
                  >
                    {node.label}
                  </text>
                );
              })}
            </g>
          </>
        ) : null}
      </svg>
      {legend?.length && legendOpen ? (
        <ul className="qf-network-legend">
          {legend.map((item) => (
            <li key={item.label}>
              <span
                className={cn(
                  'qf-network-swatch',
                  `tone-${item.tone ?? (item.series === undefined ? 'info' : 'neutral')}`,
                  item.series === undefined && 'is-secondary',
                )}
                style={toneStyle(item.series)}
                aria-hidden="true"
              />
              {item.label}
            </li>
          ))}
        </ul>
      ) : null}
      {legend?.length ? (
        <LegendCollapseButton
          inline
          className="qf-network-legend-toggle"
          collapsed={!legendOpen}
          onToggle={() => setLegendOpen((open) => !open)}
        />
      ) : null}
    </div>
  );
}
