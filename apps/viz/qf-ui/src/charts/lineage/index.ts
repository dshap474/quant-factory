/**
 * Portable lineage chart module: an ordered history (e.g. strategy versions) drawn as a
 * subway map, without data fetching. SVG only; no ECharts.
 * USAGE: import { LineageGraph } from '@quant-factory/qf-ui/charts/lineage';
 */

// --------------------------------------------------------------------------- #
// Public API
// --------------------------------------------------------------------------- #

export {
  LineageGraph,
  type LineageGraphItem,
  type LineageGraphOrientation,
  type LineageGraphProps,
} from './LineageGraph';
