/**
 * Presentation panels for the logical data and feature catalog workspace: the
 * catalog navigator (lake tree for datasets, paged list for feature sets) on the
 * shared Navigator, and the selected item's viewer.
 *
 * USAGE:
 *   <CatalogNavigator {...navigatorProps} />
 *   <CatalogSelection item={item} option={option} isLoading={isLoading} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Suspense, useMemo, useState } from 'react';

import {
  type CatalogStats,
  type LogicalCatalogItem,
  type LogicalCatalogOption,
  type LogicalCatalogResponse,
  useFullLogicalCatalog,
} from '@/lib/api/catalog';
import { useDatasetSchema } from '@/lib/api/dataset-queries';
import { featureSetLabel, featureSetSector, featureSetShape } from '@/lib/feature-set-tags';
import {
  EmptyState,
  groupNavigatorItems,
  LoadingSkeleton,
  lazyNamed,
  Navigator,
  type NavigatorNode,
  Pagination,
  SearchSelect,
  SegmentedControl,
  Stack,
  useDebouncedCallback,
} from '@/ui';

import {
  buildCatalogTree,
  type CatalogTreeDir,
  type CatalogTreeLeaf,
  type CatalogTreeNode,
  collectDirPaths,
  collectItemAncestorPaths,
  compareResolutions,
  filterCatalogTree,
  pickActiveRoot,
  timeframeMinutes,
} from './catalog-tree';
import { isRawOrderbookPath } from './charts/orderbook-view-state';
import { DatasetViewer } from './DatasetViewer';
import {
  type DataLayer,
  familyMemberLabels,
  isRawLike,
  optionKey,
  type WorkspaceParams,
} from './logical-catalog-model';

// --------------------------------------------------------------------------- #
// Types and helpers
// --------------------------------------------------------------------------- #

const FeatureFamilyWorkspace = lazyNamed(
  () => import('./FeatureFamilyWorkspace'),
  'FeatureFamilyWorkspace',
);

interface CatalogNavigatorProps {
  catalog: LogicalCatalogResponse | null;
  catalogPage: number;
  catalogPages: number;
  isData: boolean;
  isLoading: boolean;
  layer: DataLayer;
  query: string;
  selectedItem: LogicalCatalogItem | null;
  /** The URL addresses an item, so its resolution control holds a place while loading. */
  itemRequested?: boolean;
  /** Resolution of the selected option; null when nothing is explicitly selected. */
  selectedResolution?: string | null;
  /** Existing options of the selected item, in the order the detail route lists them. */
  options?: LogicalCatalogOption[];
  /** Option the detail route is showing; null when nothing is explicitly selected. */
  selectedOption?: LogicalCatalogOption | null;
  stats: CatalogStats | null;
  title: string;
  onItemSelect?: (item: LogicalCatalogItem, resolution?: string | null) => void;
  onUpdate: (updates: WorkspaceParams) => void;
}

interface CatalogSelectionProps {
  isLoading?: boolean;
  item: LogicalCatalogItem | null;
  option: LogicalCatalogOption | null;
  /** Header slot for a dataset viewer's tabs; null until the slot mounts. */
  modeControlTarget?: HTMLElement | null;
}

interface TreeContext {
  expanded: Set<string>;
  selectedItemId: string | null;
  onSelect: (leaf: CatalogTreeLeaf) => void;
  onToggle: (path: string) => void;
}

const EMPTY_OPTIONS: LogicalCatalogOption[] = [];

/** Distinct resolutions across an item's options, small to large. */
export function distinctResolutions(options: LogicalCatalogOption[]): string[] {
  const seen: string[] = [];
  for (const option of options) {
    if (!seen.includes(option.resolution)) seen.push(option.resolution);
  }
  return seen.sort(compareResolutions);
}

/** Distinct versions available at one resolution, in option order. */
export function versionsAtResolution(
  options: LogicalCatalogOption[],
  resolution: string,
): string[] {
  const seen: string[] = [];
  for (const option of options) {
    if (option.resolution === resolution && !seen.includes(option.version)) {
      seen.push(option.version);
    }
  }
  return seen;
}

/**
 * Option to open when the operator picks `resolution`: the current version when
 * it exists there, otherwise the first option at that resolution.
 */
export function optionForResolution(
  options: LogicalCatalogOption[],
  resolution: string,
  current: LogicalCatalogOption | null,
): LogicalCatalogOption | null {
  return (
    options.find(
      (option) => option.resolution === resolution && option.version === current?.version,
    ) ??
    options.find((option) => option.resolution === resolution) ??
    null
  );
}

function countLeaves(nodes: CatalogTreeNode[]): number {
  let count = 0;
  for (const node of nodes) count += node.kind === 'leaf' ? 1 : countLeaves(node.children);
  return count;
}

/** Lake-mirroring rows: directories disclose (`name/`), leaves select a dataset. */
function toNavigatorNode(node: CatalogTreeNode, context: TreeContext): NavigatorNode {
  if (node.kind === 'leaf') {
    return {
      id: node.key,
      label: node.name,
      title: `${node.name} · ${node.path}`,
      current: context.selectedItemId === node.item.id,
      onSelect: () => context.onSelect(node),
    };
  }
  return {
    id: node.key,
    label: `${node.name}/`,
    title: `${node.name} · ${node.path}/`,
    expanded: context.expanded.has(node.path),
    onToggle: () => context.onToggle(node.path),
    children: node.children.map((child) => toNavigatorNode(child, context)),
    empty: 'No datasets in this directory.',
  };
}

// --------------------------------------------------------------------------- #
// Components
// --------------------------------------------------------------------------- #

export function CatalogNavigator({
  catalog,
  catalogPage,
  catalogPages,
  isData,
  isLoading,
  layer,
  query,
  selectedItem,
  itemRequested = false,
  selectedResolution = null,
  options = EMPTY_OPTIONS,
  selectedOption = null,
  title,
  onItemSelect,
  onUpdate,
}: CatalogNavigatorProps) {
  // Search echoes locally on every keystroke; the URL param (and with it the
  // catalog query key) updates on a trailing debounce so the server sees one
  // request per pause instead of one per keystroke.
  const [search, setSearch] = useState({
    external: query,
    value: query,
    sent: null as string | null,
  });
  const debouncedSearchUpdate = useDebouncedCallback((value: string) => {
    setSearch((current) => ({ ...current, sent: value }));
    onUpdate({ q: value || null, catalogPage: null });
  }, 250);
  // Adopt external query changes (navigation, param resets) during render; our
  // own debounced write echoing back through the URL keeps local typing intact.
  const ownEcho = query === search.sent || query === search.value;
  const searchValue = search.external === query || ownEcho ? search.value : query;
  if (search.external !== query) {
    if (!ownEcho) debouncedSearchUpdate.cancel();
    setSearch((current) => ({ ...current, external: query, value: searchValue }));
  }
  const items = catalog?.items;
  const tree = useMemo(() => (isData ? buildCatalogTree(items ?? []) : []), [isData, items]);
  const visibleTree = useMemo(() => filterCatalogTree(tree, searchValue), [tree, searchValue]);
  const selectedItemId = selectedItem?.id ?? null;
  // Top-level timeframe directories become the timeframe selector, small to large;
  // one is shown at a time. Other top-level directories (`reference`) are not
  // timeframes, so they stay listed below whichever timeframe is shown. An explicit
  // operator choice sticks across selections.
  const [rootChoice, setRootChoice] = useState<string | null>(null);
  const { roots, activeRoot, treeNodes } = useMemo(() => {
    const dirs = visibleTree.filter((node): node is CatalogTreeDir => node.kind === 'dir');
    const timeframes = dirs
      .filter((node) => timeframeMinutes(node.name) !== null)
      .sort((left, right) => compareResolutions(left.name, right.name));
    const others = dirs.filter((node) => timeframeMinutes(node.name) === null);
    const selectedRootPath = collectItemAncestorPaths(visibleTree, selectedItemId)[0] ?? null;
    const root = pickActiveRoot(timeframes, rootChoice, selectedResolution, selectedRootPath);
    return {
      roots: timeframes,
      activeRoot: root,
      treeNodes: root ? [...root.children, ...others] : visibleTree,
    };
  }, [visibleTree, rootChoice, selectedResolution, selectedItemId]);

  // Keep the detail route's option on the chosen timeframe so the resolution
  // select never disagrees with the Timeframe control.
  function chooseRoot(name: string) {
    setRootChoice(name);
    if (!selectedResolution || !selectedItem) return;
    const match = selectedItem.resolutions.find(
      (option) => option.exists && option.resolution === name,
    );
    if (match) onUpdate({ option: optionKey(match) });
  }
  // Only the directories on the way to the current selection open by default so
  // the detail route reveals its leaf without unfolding the whole root.
  const defaultExpanded = useMemo(
    () =>
      searchValue.trim()
        ? collectDirPaths(treeNodes)
        : collectItemAncestorPaths(treeNodes, selectedItemId),
    [treeNodes, searchValue, selectedItemId],
  );
  // Expansion resets to the default whenever the tree or the query changes; the
  // React "adjust state during render" pattern keeps that in one render pass.
  const [expansion, setExpansion] = useState({ base: defaultExpanded, paths: defaultExpanded });
  if (expansion.base !== defaultExpanded) {
    setExpansion({ base: defaultExpanded, paths: defaultExpanded });
  }
  const expandedPaths = expansion.base === defaultExpanded ? expansion.paths : defaultExpanded;
  const expanded = useMemo(() => new Set(expandedPaths), [expandedPaths]);

  function toggleDirectory(path: string) {
    setExpansion((current) => ({
      base: current.base,
      paths: current.paths.includes(path)
        ? current.paths.filter((value) => value !== path)
        : [...current.paths, path],
    }));
  }

  function selectLeaf(leaf: CatalogTreeLeaf) {
    if (onItemSelect) {
      onItemSelect(leaf.item, leaf.resolution);
      return;
    }
    const match = leaf.item.resolutions.find((option) => option.resolution === leaf.resolution);
    onUpdate({ item: leaf.item.id, option: match ? optionKey(match) : null });
  }

  function selectFeatureSet(item: LogicalCatalogItem) {
    if (onItemSelect) {
      onItemSelect(item);
      return;
    }
    onUpdate({ item: item.id, option: null });
  }

  // Feature sets have no lake tree: the selected item's resolutions become the
  // navigator control and its versions at that resolution nest under its row.
  const featureResolutions = isData ? [] : distinctResolutions(options);
  const featureVersions =
    !isData && selectedOption ? versionsAtResolution(options, selectedOption.resolution) : [];
  function chooseResolution(resolution: string) {
    const match = optionForResolution(options, resolution, selectedOption);
    if (match) onUpdate({ option: optionKey(match) });
  }
  function chooseVersion(version: string) {
    const match = options.find(
      (option) => option.resolution === selectedOption?.resolution && option.version === version,
    );
    if (match) onUpdate({ option: optionKey(match) });
  }

  const searchLabel = isData ? 'Search datasets' : 'Search feature sets';
  const treeContext: TreeContext = {
    expanded,
    selectedItemId,
    onSelect: selectLeaf,
    onToggle: toggleDirectory,
  };
  const rows: NavigatorNode[] = isData
    ? treeNodes.map((node) => toNavigatorNode(node, treeContext))
    : (items ?? []).map((item) => {
        const shape = featureSetShape(item.asset_column);
        const row = {
          id: item.id,
          label: featureSetLabel(item.label, item.asset_column),
          title: `${item.category_path} · ${shape.title}`,
          tag: { label: shape.label },
          current: selectedItemId === item.id,
          onSelect: () => selectFeatureSet(item),
        };
        // The selected set opens in place to list its versions at the chosen
        // resolution; a set with one version stays a plain row.
        if (selectedItemId !== item.id || featureVersions.length < 2) return row;
        return {
          ...row,
          current: false,
          expanded: true,
          onToggle: () => undefined,
          children: featureVersions.map((version) => ({
            id: `${item.id}::${version}`,
            label: version,
            title: `${item.category_path} · ${selectedOption?.resolution} · ${version}`,
            current: selectedOption?.version === version,
            onSelect: () => chooseVersion(version),
          })),
        };
      });
  const controls = isData ? (
    <>
      <SegmentedControl
        ariaLabel="Data layer"
        value={layer}
        options={[
          { value: 'raw', label: 'Raw' },
          { value: 'corrected', label: 'Corrected' },
          { value: 'derived', label: 'Derived' },
        ]}
        onValueChange={(value) =>
          onUpdate({
            layer: value,
            family: null,
            domain: null,
            group: null,
            item: null,
            option: null,
            q: null,
            catalogPage: null,
          })
        }
      />
      {activeRoot ? (
        <SegmentedControl
          ariaLabel="Timeframe"
          value={activeRoot.name}
          options={roots.map((node) => ({ value: node.name, label: node.name }))}
          onValueChange={chooseRoot}
        />
      ) : isLoading ? (
        <LoadingSkeleton variant="segmented" announce={false} />
      ) : null}
    </>
  ) : selectedItem && selectedOption && featureResolutions.length ? (
    <SegmentedControl
      ariaLabel="Resolution"
      value={selectedOption.resolution}
      options={featureResolutions.map((value) => ({ value, label: value }))}
      onValueChange={chooseResolution}
    />
  ) : isLoading && itemRequested ? (
    <LoadingSkeleton variant="segmented" announce={false} />
  ) : undefined;

  const footer =
    !isData && catalogPages > 1 ? (
      <Pagination
        page={catalogPage}
        pageCount={catalogPages}
        label={`Page ${catalogPage} of ${catalogPages}`}
        disabled={isLoading}
        onPageChange={(page) => onUpdate({ catalogPage: String(page) })}
      />
    ) : undefined;

  return (
    <Navigator
      title={title}
      titleTo={isData ? '/catalog' : '/features'}
      listLabel={`${title} logical catalog`}
      mono
      density="compact"
      search={{
        id: `${isData ? 'data' : 'feature'}-catalog-search`,
        label: searchLabel,
        placeholder: searchLabel,
        value: searchValue,
        onChange: (value) => {
          setSearch((current) => ({ ...current, value }));
          debouncedSearchUpdate(value);
        },
      }}
      controls={controls}
      footer={footer}
      loading={isLoading}
      empty={isData ? 'No matching datasets' : 'No matching feature sets'}
      groups={
        isData
          ? [{ id: 'datasets', label: 'Datasets', meta: countLeaves(treeNodes), items: rows }]
          : groupNavigatorItems(rows, (row) =>
              featureSetSector(items?.find((item) => item.id === row.id)?.domain),
            )
      }
    />
  );
}

export function CatalogSelection({
  isLoading = false,
  item,
  option,
  modeControlTarget,
}: CatalogSelectionProps) {
  if (isLoading) {
    return (
      <section className="catalog-selection min-w-0" aria-busy="true">
        <Stack gap="heading" className="catalog-selection-layout">
          <div className="w-64 max-w-full">
            <LoadingSkeleton announce={false} />
          </div>
          <LoadingSkeleton variant="table" count={8} announce={false} />
        </Stack>
      </section>
    );
  }

  if (item?.kind === 'feature_set' && option?.scope === 'features') {
    return (
      <Suspense fallback={<LoadingSkeleton variant="table" label="Loading feature overview" />}>
        <FeatureFamilyWorkspace
          key={option.path}
          path={option.path}
          label={featureSetLabel(item.label, item.asset_column)}
          sector={featureSetSector(item.domain)}
          assetPanel={item.asset_column}
          description={option.description ?? item.description ?? item.category_path}
        />
      </Suspense>
    );
  }

  return (
    <section className="catalog-selection min-w-0">
      {item && option ? (
        isRawLike(item.layer) ? (
          <RawFamilyViewer
            key={`${item.id}|${option.resolution}`}
            item={item}
            option={option}
            modeControlTarget={modeControlTarget}
          />
        ) : (
          <div className="catalog-selection-layout">
            <DatasetViewer
              key={`${option.scope}:${option.path}`}
              compactChrome
              fill
              path={option.path}
              scope={option.scope}
              modeControlTarget={modeControlTarget}
            />
          </div>
        )
      ) : (
        <EmptyState title="Select a dataset" hint="Choose an item from the catalog" />
      )}
    </section>
  );
}

const ALL_MEMBERS = 'All';

/** The one folder holding every member, or null: no All for nested or orderbook families. */
function familyFolder(memberPaths: string[]): string | null {
  if (memberPaths.length < 2 || memberPaths.some(isRawOrderbookPath)) return null;
  const folders = new Set(memberPaths.map((path) => path.slice(0, path.lastIndexOf('/'))));
  return folders.size === 1 ? [...folders][0] : null;
}

/**
 * A raw family is often one parquet file per asset or partition, so the
 * summary's representative option is just the first
 * file. Offer a searchable picker over every file at the selected resolution,
 * led by All (the whole folder as one dataset) when the API can read it that way.
 */
function RawFamilyViewer({
  item,
  option,
  modeControlTarget,
}: {
  item: LogicalCatalogItem;
  option: LogicalCatalogOption;
  modeControlTarget: HTMLElement | null | undefined;
}) {
  const membersQuery = useFullLogicalCatalog({
    kind: 'dataset',
    layer: item.layer === 'corrected' ? 'corrected' : 'raw',
    family: item.category_path,
  });
  const memberPaths = useMemo(() => {
    const paths = (membersQuery.data?.items ?? []).flatMap((member) =>
      member.resolutions
        .filter((entry) => entry.exists && entry.resolution === option.resolution)
        .map((entry) => entry.path),
    );
    return [...new Set(paths)].sort();
  }, [membersQuery.data, option.resolution]);
  const labels = useMemo(() => familyMemberLabels(memberPaths), [memberPaths]);
  const familyDir = familyFolder(memberPaths);
  const allSchemaQuery = useDatasetSchema(option.scope, familyDir ?? '');
  const allPath = allSchemaQuery.isSuccess ? familyDir : null;
  const [pickedPath, setPickedPath] = useState<string | null>(null);

  if (
    membersQuery.isPending ||
    membersQuery.isPlaceholderData ||
    (familyDir && allSchemaQuery.isPending)
  ) {
    return <LoadingSkeleton variant="table" count={8} announce={false} />;
  }

  const selectedPath = pickedPath ?? allPath ?? option.path;
  const memberAll = selectedPath === allPath;
  const selectedLabel = memberAll
    ? ALL_MEMBERS
    : (labels[memberPaths.indexOf(selectedPath)] ?? null);

  return (
    <div className="catalog-selection-layout">
      {/* Not keyed by file: picking another file keeps the open tab and filters. */}
      <DatasetViewer
        compactChrome
        fill
        path={selectedPath}
        scope={option.scope}
        modeControlTarget={modeControlTarget}
        memberAll={memberAll}
        memberSelect={
          memberPaths.length > 1 ? (
            <SearchSelect
              label={labels.some((label) => label.includes('/')) ? 'file' : 'asset'}
              items={allPath ? [ALL_MEMBERS, ...labels] : labels}
              value={selectedLabel}
              onChange={(label) => {
                const path =
                  label === ALL_MEMBERS
                    ? allPath
                    : label === null
                      ? undefined
                      : memberPaths[labels.indexOf(label)];
                if (path) setPickedPath(path);
              }}
            />
          ) : undefined
        }
      />
    </div>
  );
}
