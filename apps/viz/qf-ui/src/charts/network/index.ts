/**
 * Portable network chart module: nodes and links drawn as a force-laid-out graph with
 * click-to-focus, without data fetching. SVG only; no ECharts.
 * USAGE: import { NetworkGraph } from '@quant-factory/qf-ui/charts/network';
 */

// --------------------------------------------------------------------------- #
// Public API
// --------------------------------------------------------------------------- #

export {
  NetworkGraph,
  type NetworkGraphLegendItem,
  type NetworkGraphLink,
  type NetworkGraphNode,
  type NetworkGraphNodeKind,
  type NetworkGraphProps,
} from './NetworkGraph';
