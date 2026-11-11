/**
 * Signals research layout: the shared Navigator (family → optimization
 * version) beside the routed research pages.
 *
 * USAGE:
 *   Declared as the parent route for research-oriented /signals/* paths.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useLocation } from 'react-router';
import {
  listSignalResearchVersions,
  type SignalResearchFamily,
  type SignalResearchVersion,
  signalKeys,
  useSignalResearchFamilies,
} from '@/lib/api/signals';
import { STALE } from '@/lib/api/stale-times';
import { compareVersionsDesc } from '@/lib/research-lifecycle';
import {
  familyName,
  groupNavigatorItems,
  Navigator,
  type NavigatorNode,
  SectionLayout,
  statusTone,
  useNavigatorModel,
} from '@/ui';

// --------------------------------------------------------------------------- #
// Navigator
// --------------------------------------------------------------------------- #

function SignalsNavigator() {
  const { pathname } = useLocation();
  const pathParts = pathname.split('/').filter(Boolean);
  const currentFamily = pathParts[1] ?? null;
  const currentVersion = currentFamily ? (pathParts[2] ?? null) : null;

  const familiesQuery = useSignalResearchFamilies();
  const model = useNavigatorModel<SignalResearchFamily, SignalResearchVersion>({
    families: familiesQuery.data ?? [],
    familyId: (family) => family.signal_family,
    currentId: currentFamily,
    familyMatches: (family, query) =>
      family.signal_family.toLowerCase().includes(query) ||
      familyName(family.signal_family).name.toLowerCase().includes(query) ||
      family.versions.some((version) => version.toLowerCase().includes(query)),
    childMatches: (version, query) => version.memory_version.toLowerCase().includes(query),
    childrenQueryKey: (family) => signalKeys.researchVersions(family),
    loadChildren: (family, signal) => listSignalResearchVersions(family, signal),
    staleTime: STALE.list,
    sortChildren: compareVersionsDesc,
  });
  const query = model.query.trim();

  const items: NavigatorNode[] = model.visibleFamilies.map((family) => {
    const id = family.signal_family;
    const isCurrentFamily = id === currentFamily;
    const { children, loading, error } = model.childrenOf(id);
    const visible = children.filter(
      (version) =>
        model.childVisible(version) ||
        (isCurrentFamily && version.memory_version === currentVersion),
    );
    return {
      id,
      label: familyName(id).name,
      to: `/signals/${id}`,
      current: isCurrentFamily && currentVersion === null,
      expanded: model.isExpanded(id),
      onToggle: () => model.toggle(id),
      loading,
      error,
      empty: children.length > 0 ? `No versions match “${query}”.` : 'No versions yet.',
      children: visible.map((version) => ({
        id: version.memory_version,
        label: version.memory_version,
        to: `/signals/${id}/${version.memory_version}`,
        current: isCurrentFamily && version.memory_version === currentVersion,
        tag: {
          label: version.lifecycle_status ?? version.display_state,
          tone: statusTone(version.lifecycle_status ?? version.display_state),
        },
      })),
    };
  });

  return (
    <Navigator
      title="Signals"
      titleTo="/signals"
      listLabel="Signal hierarchy"
      search={{
        id: 'signal-search',
        label: 'Search signal family or version',
        placeholder: 'Search signals',
        value: model.query,
        onChange: model.setQuery,
      }}
      loading={familiesQuery.isLoading}
      error={
        familiesQuery.error
          ? `Failed to load signal research catalog: ${familiesQuery.error.message}`
          : null
      }
      empty={query ? `No signals match “${query}”.` : 'No signal families yet.'}
      groups={groupNavigatorItems(items, (item) => familyName(item.id).sector)}
    />
  );
}

// --------------------------------------------------------------------------- #
// Layout
// --------------------------------------------------------------------------- #

export function SignalsLayout() {
  return <SectionLayout navigator={<SignalsNavigator />} />;
}
