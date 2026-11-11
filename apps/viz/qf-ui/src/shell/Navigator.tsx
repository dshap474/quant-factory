/**
 * Section navigator: the shared secondary navigation column of every section
 * workspace. Leaf links and disclosure-row navigation go through the host router
 * adapter (`QfRouterProvider`).
 * Owns the collapse state, loading/error/empty states and the row tree; consumers
 * describe their hierarchy as `NavigatorNode` data. The header band shows `title`
 * (the section label) and nothing else; every control (collapse, search, width
 * toggle, `headerActions`) lives in the bottom bar under the scrolling list.
 * Rows whose text is cut by the navigator width show the full text in a hover/focus
 * popout (NavigatorOverflowPopout).
 *
 * USAGE:
 *   <Navigator
 *     title="Signals"
 *     listLabel="Signal hierarchy"
 *     search={{ id: 'signal-search', label: 'Search signals', placeholder: 'Search signals', value, onChange }}
 *     loading={isLoading}
 *     error={error ? 'Failed to load signal research catalog.' : null}
 *     empty={`No signals match “${query}”.`}
 *     items={[
 *       {
 *         id: 'family',
 *         label: 'family',
 *         to: '/signals/family',
 *         expanded: true,
 *         onToggle: () => toggle('family'),
 *         children: [
 *           { id: 'v004', label: 'v004', to: '/signals/family/v004', current: true, tag: { label: 'supported', tone: 'success' } },
 *         ],
 *       },
 *     ]}
 *   />
 *   <Navigator title="ML Engine" density="compact" groups={[{ id: 'runs', label: 'Runs', meta: runs.length, items }]} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { ChevronRight } from 'lucide-react';
import {
  type ComponentProps,
  type CSSProperties,
  type ReactNode,
  useEffect,
  useState,
} from 'react';

import { SectionNavigator } from '../frame/SectionWorkspace';
import { cn } from '../lib/cn';
import { ICON_SIZE_SM, ICON_STROKE } from '../lib/icon';
import type { Tone } from '../lib/tone';
import { type QfResolvedRouterAdapter, useQfRouter } from '../router/RouterAdapter';
import { LoadingSkeleton } from '../state/LoadingSkeleton';
import { StateMessage } from '../state/StateMessage';
import { useNavigatorOverflowPopout } from './NavigatorOverflowPopout';
import { NavigatorSearch } from './NavigatorSearch';

import './Navigator.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface NavigatorTag {
  label: string;
  /** Status tone for the tag text; derive it with `statusTone(label)`. Defaults to neutral. */
  tone?: Tone;
}

export interface NavigatorNode {
  id: string;
  label: ReactNode;
  /** Leaf route, or the route a disclosure row opens when clicked. */
  to?: string;
  /** Called when a leaf row is activated. */
  onSelect?: () => void;
  current?: boolean;
  /** Leaf rows only: pressed state of the row control. */
  pressed?: boolean;
  /** Leaf rows only: trailing controls rendered beside the row, outside its button. */
  actions?: ReactNode;
  tag?: NavigatorTag;
  /** Leading glyph such as `01`. */
  glyph?: string;
  /** Leading slot such as a `StatusDot`. */
  leading?: ReactNode;
  /** Secondary lines stacked under the label. */
  detail?: ReactNode;
  /** Trailing slot. */
  meta?: ReactNode;
  title?: string;
  /** Present (even when empty) on disclosure rows. */
  children?: NavigatorNode[];
  expanded?: boolean;
  onToggle?: () => void;
  /** Child-list states for lazily loaded children. */
  loading?: boolean;
  error?: string | null;
  empty?: string;
}

export interface NavigatorGroup {
  id: string;
  label?: ReactNode;
  meta?: ReactNode;
  /** Label row toggles the group open/closed (trailing chevron); open by default, always open while searching. */
  collapsible?: boolean;
  items: NavigatorNode[];
}

export interface NavigatorProps {
  /** Section label shown in the header band (sentence case, e.g. "Strategies"). */
  title: string;
  /** The section's home route; the header title links there. */
  titleTo?: string;
  className?: string;
  /** Controlled collapse state; uncontrolled navigators start collapsed on compact viewports. */
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
  search?: ComponentProps<typeof NavigatorSearch>;
  controls?: ReactNode;
  /** Footer slot above the collapse button; hidden while collapsed. */
  footer?: ReactNode;
  items?: NavigatorNode[];
  groups?: NavigatorGroup[];
  /** aria-label of the row list; defaults to `${title} hierarchy`. */
  listLabel?: string;
  loading?: boolean;
  error?: string | null;
  empty?: string;
  /** No-op kept for compatibility: every navigator label is sans (R38). */
  mono?: boolean;
  /** No-op kept for compatibility: rows are one 28px height. */
  density?: 'default' | 'compact';
  /** Collapse after a leaf selection on compact viewports. */
  collapseOnSelect?: boolean;
  /** Which workspace edge the navigator docks to. Default 'start'. */
  side?: 'start' | 'end';
  /** Collapsed presentation; 'strip' keeps a control-height column with a vertical title. */
  collapsedVariant?: 'tile' | 'strip';
  /** Bottom-bar slot used when `search` is not given; `search` wins when both are set. */
  headerActions?: ReactNode;
  /** Controlled narrow width (see SectionNavigator); defaults to the shared width provider. */
  narrow?: boolean;
  onNarrowChange?: (narrow: boolean) => void;
}

interface RowContext {
  Link: QfResolvedRouterAdapter['Link'];
  onLeafSelect: () => void;
  openRoute: (to: string) => void;
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

export const COMPACT_VIEWPORT_QUERY = '(max-width: 767px)';

/** Whether the viewport is phone-sized (navigators start collapsed); false without a DOM. */
export function isCompactViewport(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia(COMPACT_VIEWPORT_QUERY).matches
    : false;
}

export interface GroupNavigatorItemsOptions {
  /** Label for items whose `groupOf` is null; that group always sorts last. */
  otherLabel?: string;
}

/**
 * Split top-level items into collapsible labeled groups (label sorted, item order
 * kept), e.g. families by sector:
 * `groupNavigatorItems(items, (item) => familyName(item.id).sector)`.
 */
export function groupNavigatorItems(
  items: NavigatorNode[],
  groupOf: (item: NavigatorNode) => string | null,
  { otherLabel = 'Other' }: GroupNavigatorItemsOptions = {},
): NavigatorGroup[] {
  const buckets = new Map<string | null, NavigatorNode[]>();
  for (const item of items) {
    const key = groupOf(item);
    buckets.set(key, [...(buckets.get(key) ?? []), item]);
  }
  const labels = [...buckets.keys()]
    .filter((key): key is string => key !== null)
    .sort((left, right) => left.localeCompare(right));
  const groups = labels.map((label) => {
    const grouped = buckets.get(label) ?? [];
    return { id: label, label, collapsible: true, items: grouped };
  });
  const other = buckets.get(null);
  if (other) groups.push({ id: '__other__', label: otherLabel, collapsible: true, items: other });
  return groups;
}

function depthStyle(depth: number): CSSProperties {
  return { '--ui-navigator-depth': depth } as CSSProperties;
}

// --------------------------------------------------------------------------- #
// Rows
// --------------------------------------------------------------------------- #

interface NodeListProps {
  items: NavigatorNode[];
  depth: number;
  context: RowContext;
}

function NodeList({ items, depth, context }: NodeListProps) {
  return (
    <ul className={depth === 0 ? 'ui-navigator-items' : 'ui-navigator-children'}>
      {items.map((node) => (
        <NavigatorRow key={node.id} node={node} depth={depth} context={context} />
      ))}
    </ul>
  );
}

interface NavigatorRowProps {
  node: NavigatorNode;
  depth: number;
  context: RowContext;
}

function NavigatorRow({ node, depth, context }: NavigatorRowProps) {
  const isDisclosure = node.children !== undefined;
  const expanded = isDisclosure && Boolean(node.expanded);
  const rowClass = cn(
    'ui-navigator-row',
    isDisclosure ? 'is-disclosure' : 'is-leaf',
    depth === 0 && 'is-root',
    node.current && 'is-current',
  );
  const content = (
    <>
      {node.glyph !== undefined ? (
        <span className="ui-navigator-glyph" aria-hidden="true">
          {node.glyph}
        </span>
      ) : null}
      {node.leading !== undefined ? (
        <span className="ui-navigator-leading">{node.leading}</span>
      ) : null}
      <span className="ui-navigator-copy">
        <span className="ui-navigator-label">{node.label}</span>
        {node.detail !== undefined ? (
          <span className="ui-navigator-detail">{node.detail}</span>
        ) : null}
      </span>
      {node.tag ? (
        <span className="ui-navigator-tag" data-tone={node.tag.tone ?? 'neutral'}>
          {node.tag.label}
        </span>
      ) : null}
      {node.meta !== undefined ? <span className="ui-navigator-meta">{node.meta}</span> : null}
      {isDisclosure ? (
        <span className={cn('ui-navigator-chevron', expanded && 'is-open')} aria-hidden="true">
          <ChevronRight size={ICON_SIZE_SM} strokeWidth={ICON_STROKE} />
        </span>
      ) : null}
    </>
  );

  const select = () => {
    node.onSelect?.();
    context.onLeafSelect();
  };

  let row: ReactNode;
  if (isDisclosure) {
    row = (
      <button
        type="button"
        className={rowClass}
        style={depthStyle(depth)}
        title={node.title}
        aria-expanded={expanded}
        aria-current={node.current ? 'true' : undefined}
        onClick={() => {
          node.onToggle?.();
          if (node.to !== undefined) context.openRoute(node.to);
        }}
      >
        {content}
      </button>
    );
  } else if (node.to !== undefined) {
    const { Link } = context;
    row = (
      <Link
        to={node.to}
        className={rowClass}
        style={depthStyle(depth)}
        title={node.title}
        aria-current={node.current ? 'page' : undefined}
        aria-pressed={node.pressed}
        onClick={select}
      >
        {content}
      </Link>
    );
  } else {
    row = (
      <button
        type="button"
        className={rowClass}
        style={depthStyle(depth)}
        title={node.title}
        aria-current={node.current ? 'true' : undefined}
        aria-pressed={node.pressed}
        onClick={select}
      >
        {content}
      </button>
    );
  }

  if (!isDisclosure && node.actions !== undefined) {
    return (
      <li className="ui-navigator-item has-actions">
        {row}
        <span className="ui-navigator-actions">{node.actions}</span>
      </li>
    );
  }

  return (
    <li className={cn('ui-navigator-item', expanded && 'is-expanded')}>
      {row}
      {expanded ? <NodeChildren node={node} depth={depth + 1} context={context} /> : null}
    </li>
  );
}

function NodeChildren({ node, depth, context }: NavigatorRowProps) {
  if (node.loading) {
    return (
      <div className="ui-navigator-children-state">
        <LoadingSkeleton variant="line" count={3} announce={false} />
      </div>
    );
  }
  if (node.error) {
    return (
      <StateMessage state="error" compact className="ui-navigator-message">
        {node.error}
      </StateMessage>
    );
  }
  const children = node.children ?? [];
  if (children.length === 0) {
    return (
      <StateMessage compact className="ui-navigator-message">
        {node.empty ?? 'Nothing here yet.'}
      </StateMessage>
    );
  }
  return <NodeList items={children} depth={depth} context={context} />;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Navigator({
  title,
  titleTo,
  className,
  collapsed: collapsedProp,
  onCollapsedChange,
  search,
  controls,
  footer,
  items,
  groups,
  listLabel,
  loading = false,
  error = null,
  empty = 'Nothing here yet.',
  collapseOnSelect = true,
  side = 'start',
  collapsedVariant = 'tile',
  headerActions,
  narrow,
  onNarrowChange,
}: NavigatorProps) {
  const { Link, useNavigate, usePathname } = useQfRouter();
  const navigate = useNavigate();
  const pathname = usePathname();
  const [collapsedState, setCollapsedState] = useState(isCompactViewport);
  const [closedGroups, setClosedGroups] = useState<ReadonlySet<string>>(new Set());
  const searching = Boolean(search?.value.trim());
  const toggleGroup = (id: string) =>
    setClosedGroups((previous) => {
      const next = new Set(previous);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  const collapsed = collapsedProp ?? collapsedState;
  const overflowPopout = useNavigatorOverflowPopout(side);

  const setCollapsed = (next: boolean) => {
    if (collapsedProp === undefined) setCollapsedState(next);
    onCollapsedChange?.(next);
  };

  // Shrinking into a phone-sized viewport collapses the navigator, as loading at that size does.
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const query = window.matchMedia(COMPACT_VIEWPORT_QUERY);
    const onChange = (event: MediaQueryListEvent) => {
      if (!event.matches || collapsed) return;
      if (collapsedProp === undefined) setCollapsedState(true);
      onCollapsedChange?.(true);
    };
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, [collapsed, collapsedProp, onCollapsedChange]);

  const resolvedGroups: NavigatorGroup[] = groups ?? [{ id: 'items', items: items ?? [] }];
  const total = resolvedGroups.reduce((count, group) => count + group.items.length, 0);
  const context: RowContext = {
    Link,
    onLeafSelect: () => {
      if (collapseOnSelect && isCompactViewport()) setCollapsed(true);
    },
    openRoute: (to) => {
      // A route that only adds a query (?q=) to the current page is already open.
      if (to.split(/[?#]/)[0] !== pathname) navigate(to);
    },
  };

  let body: ReactNode;
  if (loading) {
    body = (
      <div className="ui-navigator-loading">
        <LoadingSkeleton variant="line" count={8} label={`Loading ${title}`} />
      </div>
    );
  } else if (error) {
    body = (
      <StateMessage state="error" compact className="ui-navigator-message">
        {error}
      </StateMessage>
    );
  } else if (total === 0) {
    body = (
      <StateMessage compact className="ui-navigator-message">
        {empty}
      </StateMessage>
    );
  } else {
    body = (
      <nav
        className="ui-navigator-list"
        aria-label={listLabel ?? `${title} hierarchy`}
        {...overflowPopout.listProps}
      >
        {resolvedGroups.map((group) => {
          const open = !group.collapsible || searching || !closedGroups.has(group.id);
          const meta =
            group.meta !== undefined ? (
              <span className="ui-navigator-group-meta">{group.meta}</span>
            ) : null;
          let label: ReactNode = null;
          if (group.collapsible) {
            label = (
              <button
                type="button"
                className="ui-navigator-group-label is-collapsible"
                aria-expanded={open}
                onClick={() => toggleGroup(group.id)}
              >
                <span>{group.label}</span>
                {meta}
                <span className={cn('ui-navigator-chevron', open && 'is-open')} aria-hidden="true">
                  <ChevronRight size={ICON_SIZE_SM} strokeWidth={ICON_STROKE} />
                </span>
              </button>
            );
          } else if (group.label !== undefined || group.meta !== undefined) {
            label = (
              <div className="ui-navigator-group-label">
                <span>{group.label}</span>
                {meta}
              </div>
            );
          }
          return (
            <div key={group.id} className="ui-navigator-group">
              {label}
              {open ? <NodeList items={group.items} depth={0} context={context} /> : null}
            </div>
          );
        })}
      </nav>
    );
  }

  return (
    <SectionNavigator
      title={title}
      titleTo={titleTo}
      className={cn('ui-navigator', className)}
      collapsed={collapsed}
      onToggleCollapse={() => setCollapsed(!collapsed)}
      side={side}
      collapsedVariant={collapsedVariant}
      narrow={narrow}
      onNarrowChange={onNarrowChange}
      headerActions={search ? <NavigatorSearch {...search} /> : headerActions}
      controls={controls}
      footerControls={collapsed ? undefined : footer}
    >
      {body}
      {overflowPopout.popout}
    </SectionNavigator>
  );
}
