/**
 * Strategies section layout: the shared Navigator (strategy type → memory
 * version, extension suites first) beside the routed strategy pages. The
 * Overview (/strategies) and Backtesting (/strategies/backtesting) tabs select
 * no navigator row.
 *
 * USAGE:
 *   Declared as the parent route for /strategies/*.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useLocation } from 'react-router';
import { extensionStrategyRows } from '@/extensions';
import { STALE } from '@/lib/api/stale-times';
import {
  listStrategyVersions,
  type StrategyTypeSummary,
  type StrategyVersionSummary,
  strategyKeys,
  useStrategyTypes,
} from '@/lib/api/strategies';
import { compareVersionsDesc } from '@/lib/research-lifecycle';
import {
  familyName,
  groupNavigatorItems,
  Navigator,
  type NavigatorNode,
  type NavigatorTag,
  SectionLayout,
  statusTone,
  useNavigatorModel,
} from '@/ui';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

/** Memory versions are `vNNN`; any other segment (a suite page) is not a version row. */
const MEMORY_VERSION = /^v\d{3}$/;

/** Promoted versions carry no tag; surfaced ones show their display state. */
function versionTag(version: StrategyVersionSummary): NavigatorTag | undefined {
  if (version.display_state === 'promoted') return undefined;
  return {
    label: version.has_surface
      ? version.display_state
      : (version.lifecycle_status ?? version.display_state),
    tone: statusTone(
      version.has_surface
        ? version.display_state
        : (version.lifecycle_status ?? version.display_state),
    ),
  };
}

// --------------------------------------------------------------------------- #
// Navigator
// --------------------------------------------------------------------------- #

function StrategiesNavigator() {
  const { pathname } = useLocation();
  const pathParts = pathname.split('/').filter(Boolean);
  // The Backtesting tab is a page, not a strategy type to load versions for.
  const currentType = pathParts[1] === 'backtesting' ? null : (pathParts[1] ?? null);
  const rawVersion = pathParts[2] ?? null;
  // Suite pages must not light up as memory-version rows.
  const currentVersion = rawVersion && MEMORY_VERSION.test(rawVersion) ? rawVersion : null;

  const typesQuery = useStrategyTypes();
  const strategyTypes = typesQuery.data ?? [];
  const model = useNavigatorModel<StrategyTypeSummary, StrategyVersionSummary>({
    families: strategyTypes,
    familyId: (type) => type.strategy_type,
    currentId: currentType,
    familyMatches: (type, query) =>
      type.strategy_type.toLowerCase().includes(query) ||
      familyName(type.strategy_type).name.toLowerCase().includes(query) ||
      type.versions.some((version) => version.toLowerCase().includes(query)),
    childMatches: (version, query) => version.memory_version.toLowerCase().includes(query),
    childrenQueryKey: (type) => strategyKeys.versions(type),
    loadChildren: (type, signal) => listStrategyVersions(type, signal),
    staleTime: STALE.list,
    sortChildren: compareVersionsDesc,
  });
  const query = model.query.trim();

  // Extension suites without an API strategy type link straight to their page.
  const extensionItems: NavigatorNode[] = extensionStrategyRows()
    .filter(
      (row) =>
        !strategyTypes.some((type) => type.strategy_type === row.key) &&
        row.key.toLowerCase().includes(model.queryNormalized),
    )
    .map((row) => ({
      id: row.key,
      label: familyName(row.key).name,
      to: row.href ?? '/strategies',
      current: currentType === row.key,
    }));

  const typeItems: NavigatorNode[] = model.visibleFamilies.map((type) => {
    const id = type.strategy_type;
    const isCurrentType = id === currentType;
    const { children, loading, error } = model.childrenOf(id);
    const visible = children.filter(
      (version) =>
        model.childVisible(version) || (isCurrentType && version.memory_version === currentVersion),
    );
    return {
      id,
      label: familyName(id).name,
      to: `/strategies/${id}`,
      current: isCurrentType && currentVersion === null,
      expanded: model.isExpanded(id),
      onToggle: () => model.toggle(id),
      loading,
      error,
      empty: children.length > 0 ? `No versions match “${query}”.` : 'No versions yet.',
      children: visible.map((version) => ({
        id: version.memory_version,
        label: version.memory_version,
        to: `/strategies/${id}/${version.memory_version}`,
        current: isCurrentType && version.memory_version === currentVersion,
        tag: versionTag(version),
      })),
    };
  });

  return (
    <Navigator
      title="Strategies"
      titleTo="/strategies"
      listLabel="Strategy hierarchy"
      search={{
        id: 'strategy-search',
        label: 'Search strategy type or version',
        placeholder: 'Search strategies',
        value: model.query,
        onChange: model.setQuery,
      }}
      loading={typesQuery.isLoading}
      error={
        typesQuery.error ? `Failed to load strategy catalog: ${typesQuery.error.message}` : null
      }
      empty={query ? `No strategies match “${query}”.` : 'No strategy types yet.'}
      groups={groupNavigatorItems(
        [...extensionItems, ...typeItems],
        (item) => familyName(item.id).sector,
      )}
    />
  );
}

// --------------------------------------------------------------------------- #
// Layout
// --------------------------------------------------------------------------- #

export function StrategiesLayout() {
  return <SectionLayout navigator={<StrategiesNavigator />} />;
}
