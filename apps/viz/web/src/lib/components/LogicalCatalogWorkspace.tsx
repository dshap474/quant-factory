/**
 * URL-backed logical catalog workspace: the shared-Navigator catalog beside the
 * selected item's viewer, or the physical explorer when `?view=explorer` is set.
 *
 * USAGE:
 *   <LogicalCatalogWorkspace title="Data" catalogKind="dataset" catalog={catalog} … />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { type ReactNode, useState } from 'react';
import { useSearchParams } from 'react-router';
import type {
  CatalogStats,
  LogicalCatalogItem,
  LogicalCatalogOption,
  LogicalCatalogResponse,
} from '@/lib/api/catalog';
import { compareNatural, PageHeader, SectionWorkspace, useSearchParamsPatch } from '@/ui';

import { DatasetExplorer } from './DatasetExplorer';
import { CatalogNavigator, CatalogSelection } from './LogicalCatalogPanels';
import { type DataLayer, optionKey, type WorkspaceParams } from './logical-catalog-model';

// --------------------------------------------------------------------------- #
// Types and helpers
// --------------------------------------------------------------------------- #

export type CatalogKind = 'dataset' | 'feature_set';

export interface LogicalCatalogWorkspaceProps {
  title: string;
  subtitle: string;
  rootLabel: string;
  catalog: LogicalCatalogResponse | null;
  stats: CatalogStats | null;
  catalogKind: CatalogKind;
  isLoading?: boolean;
  overview?: ReactNode;
  onItemSelect?: (item: LogicalCatalogItem, resolution?: string | null) => void;
  selectFirstItem?: boolean;
}

function compareOptions(left: LogicalCatalogOption, right: LogicalCatalogOption): number {
  if (left.version === 'latest') return -1;
  if (right.version === 'latest') return 1;
  return (
    compareNatural(left.version, right.version) || compareNatural(left.resolution, right.resolution)
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function LogicalCatalogWorkspace({
  title,
  subtitle,
  rootLabel,
  catalog,
  stats,
  catalogKind,
  isLoading = false,
  overview,
  onItemSelect,
  selectFirstItem = true,
}: LogicalCatalogWorkspaceProps) {
  const [searchParams] = useSearchParams();
  const patchSearchParams = useSearchParamsPatch();
  const [modeControlTarget, setModeControlTarget] = useState<HTMLDivElement | null>(null);
  const explorer = searchParams.get('view') === 'explorer';
  const requestedLayer = searchParams.get('layer');
  const layer: DataLayer =
    requestedLayer === 'raw' || requestedLayer === 'corrected'
      ? requestedLayer
      : requestedLayer === 'derived' || catalogKind !== 'dataset'
        ? 'derived'
        : 'raw';

  function updateWorkspaceParams(updates: WorkspaceParams) {
    patchSearchParams(updates, { replace: true });
  }

  const isData = catalogKind === 'dataset';
  const catalogPage = Math.floor((catalog?.offset ?? 0) / Math.max(catalog?.limit ?? 100, 1)) + 1;
  const catalogPages = Math.max(1, Math.ceil((catalog?.total ?? 0) / (catalog?.limit ?? 100)));
  const requestedItemId = searchParams.get('item');
  // Raw families are addressed by `family` on the detail route (summary ids are
  // not carried in the URL), so fall back to a category-path match for datasets.
  const requestedFamily = isData ? searchParams.get('family') : null;
  const selectedItem =
    catalog?.items.find((item) => item.id === requestedItemId) ??
    (requestedFamily
      ? catalog?.items.find((item) => item.category_path === requestedFamily)
      : null) ??
    (selectFirstItem ? catalog?.items[0] : null) ??
    null;
  const options = [...(selectedItem?.resolutions ?? [])]
    .filter((item) => item.exists)
    .sort(compareOptions);
  const selectedOption =
    options.find((item) => optionKey(item) === searchParams.get('option')) ?? options[0] ?? null;
  // Only an explicitly addressed item drives the navigator timeframe; the list
  // route (which may fall back to the first item) keeps its own root choice.
  const explicitSelection = Boolean(requestedItemId || requestedFamily);
  const featureOwnsHeader =
    !explorer &&
    !overview &&
    !isLoading &&
    selectedItem?.kind === 'feature_set' &&
    selectedOption?.scope === 'features';

  const content = explorer ? (
    <DatasetExplorer
      scope={catalogKind === 'feature_set' ? 'features' : 'data'}
      rootLabel={rootLabel}
    />
  ) : (
    (overview ?? (
      <CatalogSelection
        isLoading={isLoading}
        item={selectedItem}
        option={selectedOption}
        modeControlTarget={modeControlTarget}
      />
    ))
  );

  return (
    <SectionWorkspace
      className="catalog-terminal-workspace"
      contentMode={featureOwnsHeader ? 'fill' : 'scroll'}
      navigator={
        <CatalogNavigator
          catalog={catalog}
          catalogPage={catalogPage}
          catalogPages={catalogPages}
          isData={isData}
          isLoading={isLoading}
          layer={layer}
          query={searchParams.get('q') ?? ''}
          selectedItem={selectedItem}
          itemRequested={explicitSelection}
          selectedResolution={explicitSelection ? (selectedOption?.resolution ?? null) : null}
          options={options}
          selectedOption={explicitSelection ? selectedOption : null}
          stats={stats}
          title={title}
          onItemSelect={onItemSelect}
          onUpdate={updateWorkspaceParams}
        />
      }
    >
      {featureOwnsHeader ? null : (
        <PageHeader
          title={selectedItem?.label ?? title}
          subtitle={
            selectedItem?.description ??
            selectedItem?.category_labels?.join(' / ') ??
            selectedItem?.category_path ??
            subtitle
          }
          tabs={
            explorer || overview ? undefined : (
              <div ref={setModeControlTarget} className="contents" />
            )
          }
        />
      )}
      <div className="catalog-terminal-content">{content}</div>
    </SectionWorkspace>
  );
}
