/**
 * Detailed Data workspace for one logical series.
 *
 * USAGE:
 *   Routed at /catalog/view?layer=derived&item=<logical-id>
 *   Routed at /catalog/view?layer=raw&family=<category-path>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useSearchParams } from 'react-router';

import { type LogicalCatalogItem, useFullLogicalCatalog } from '@/lib/api/catalog';
import { LogicalCatalogWorkspace } from '@/lib/components/LogicalCatalogWorkspace';
import {
  buildCatalogDetailParams,
  isRawLike,
  readDataLayer,
} from '@/lib/components/logical-catalog-model';
import { ErrorPanel, isLoadingData, PageHeader } from '@/ui';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function CatalogDetailPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const layer = readDataLayer(searchParams.get('layer'));
  // The tree navigator mirrors the whole layer, so the sidebar query carries no
  // facet filters and no paging — the same shape the /catalog overview uses.
  const catalogQuery = useFullLogicalCatalog({
    kind: 'dataset',
    layer,
    summary: isRawLike(layer),
    q: searchParams.get('q') ?? '',
  });
  const catalogLoading = isLoadingData(catalogQuery);
  // The workspace owns its loading skeletons (its controls stay mounted); only a
  // failure with nothing to show replaces it.
  const catalogFailed = catalogQuery.data === undefined ? catalogQuery.error : null;

  function selectItem(item: LogicalCatalogItem, resolution?: string | null) {
    setSearchParams(buildCatalogDetailParams(searchParams, item, layer, resolution), {
      replace: true,
    });
  }

  return (
    <div className="catalog-terminal-page">
      {catalogFailed ? <PageHeader title="Data" subtitle="Dataset unavailable" /> : null}
      <div className="catalog-terminal-query">
        {catalogFailed ? (
          <ErrorPanel message={catalogFailed.message} onRetry={() => void catalogQuery.refetch()} />
        ) : (
          <LogicalCatalogWorkspace
            title="Data"
            subtitle=""
            rootLabel="db/data"
            catalog={catalogQuery.data ?? null}
            stats={null}
            catalogKind="dataset"
            isLoading={catalogLoading}
            onItemSelect={selectItem}
            selectFirstItem={false}
          />
        )}
      </div>
    </div>
  );
}
