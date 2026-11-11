/**
 * Public surface of qf-ui, the Quant Factory design system: primitives, layout,
 * data display, loading/empty/error state, page frames, shell controls, tokens, and
 * the router adapter. Charts live behind the `@quant-factory/qf-ui/charts*` subpaths so this
 * barrel never pulls ECharts into a bundle; tables live behind `@quant-factory/qf-ui/tables*`.
 *
 * USAGE:
 *   import { Button, PageHeader, Surface } from '@quant-factory/qf-ui';
 *   import '@quant-factory/qf-ui/styles.css'; // from the host's Tailwind entry
 *
 * Inside qf-ui import siblings by relative path, never through this barrel.
 */

// --------------------------------------------------------------------------- #
// Cascade layers (first, so kit CSS never precedes the layer order)
// --------------------------------------------------------------------------- #

import './styles/layers.css';

// --------------------------------------------------------------------------- #
// Primitives
// --------------------------------------------------------------------------- #

export * from './primitives/Badge';
export * from './primitives/Button';
export * from './primitives/CodeBlock';
export * from './primitives/DateRangePicker';
export * from './primitives/Field';
export * from './primitives/HighlightedText';
export * from './primitives/Identifier';
export * from './primitives/ImageFigure';
export * from './primitives/Input';
export * from './primitives/Kbd';
export * from './primitives/Link';
export * from './primitives/PlaybackScrubber';
export * from './primitives/Prose';
export * from './primitives/RelativeTime';
export * from './primitives/RouteTabs';
export * from './primitives/SearchSelect';
export * from './primitives/SegmentedControl';
export * from './primitives/Select';
export * from './primitives/Stat';
export * from './primitives/StatCard';
export * from './primitives/StepNav';
export * from './primitives/Surface';
export * from './primitives/Text';
export * from './primitives/Timestamp';
export * from './primitives/TimestampSelector';

// --------------------------------------------------------------------------- #
// Layout
// --------------------------------------------------------------------------- #

export * from './layout/ChartGrid';
export * from './layout/Cluster';
export * from './layout/Columns';
export * from './layout/Disclosure';
export * from './layout/DocumentLayout';
export * from './layout/Grid';
export * from './layout/Inset';
export * from './layout/ListDetail';
export * from './layout/ScrollArea';
export * from './layout/Section';
export * from './layout/SplitRow';
export * from './layout/Stack';
export * from './layout/StatGrid';
export * from './layout/Toolbar';

// --------------------------------------------------------------------------- #
// Data
// --------------------------------------------------------------------------- #

export * from './data/ColumnBrowser';
export * from './data/DataList';
export * from './data/FacetedFilter';
export * from './data/IndexBar';
export * from './data/Pagination';
export * from './data/ProgressBar';
export * from './data/RecordList';
export * from './data/RollingNumber';
export * from './data/SelectList';
export * from './data/StageBar';
export * from './data/StepStrip';
export * from './data/TokenUsage';
export * from './data/usePagedRows';

// --------------------------------------------------------------------------- #
// State
// --------------------------------------------------------------------------- #

export * from './state/Banner';
export * from './state/EmptyState';
export * from './state/ErrorPanel';
export * from './state/LoadingSkeleton';
export * from './state/QueryState';
export * from './state/StateMessage';
export * from './state/Status';
export * from './state/WorkspaceFallback';

// --------------------------------------------------------------------------- #
// Overlay
// --------------------------------------------------------------------------- #

export * from './overlay/Dialog';
export * from './overlay/DropdownMenu';
export * from './overlay/InfoTip';
export * from './overlay/LazyToaster';
export * from './overlay/Popover';
export * from './overlay/placement';
export * from './overlay/Sheet';
export * from './overlay/Toast';
export * from './overlay/Tooltip';
export * from './overlay/toast-store';

// --------------------------------------------------------------------------- #
// Command
// --------------------------------------------------------------------------- #

export * from './command/CommandPalette';

// --------------------------------------------------------------------------- #
// Frame
// --------------------------------------------------------------------------- #

export * from './frame/PageHeader';
export * from './frame/PageShell';
export * from './frame/proseTypography';
export * from './frame/Reader';
export * from './frame/SectionWorkspace';
export * from './frame/TerminalPage';
export * from './frame/WorkspaceHeaderPortal';
export * from './frame/WorkspaceToolbar';

// --------------------------------------------------------------------------- #
// Shell
// --------------------------------------------------------------------------- #

export * from './shell/Navigator';
export * from './shell/NavigatorOverflowPopout';
export * from './shell/NavigatorSearch';
export * from './shell/SidebarCollapseButton';
export * from './shell/SidebarShell';
export * from './shell/useTreeNavigatorState';

// --------------------------------------------------------------------------- #
// Router adapter
// --------------------------------------------------------------------------- #

export * from './router/RouterAdapter';
export * from './router/useSearchParamChoice';
export * from './router/useSearchParamState';
export * from './router/useSearchParamsPatch';

// --------------------------------------------------------------------------- #
// Lib
// --------------------------------------------------------------------------- #

export * from './lib/cn';
export * from './lib/compare';
export * from './lib/extent';
export * from './lib/heat';
export * from './lib/humanize';
export * from './lib/icon';
export * from './lib/lazy-named';
export * from './lib/number-format';
export * from './lib/plural';
export * from './lib/time-format';
export * from './lib/tone';
export * from './lib/truncate';
export * from './lib/typing-target';
export * from './lib/use-debounced-callback';
export * from './lib/use-now';

// --------------------------------------------------------------------------- #
// Tokens
// --------------------------------------------------------------------------- #

export * from './tokens';
