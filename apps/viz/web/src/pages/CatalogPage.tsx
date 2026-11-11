/**
 * Data overview — map the canonical pipeline before opening a detail workspace.
 *
 * USAGE:
 *   Routed at /catalog
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useNavigate, useSearchParams } from 'react-router';

import { type LogicalCatalogItem, useFullLogicalCatalog } from '@/lib/api/catalog';
import { DataLakeMap } from '@/lib/components/DataLakeMap';
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

export function CatalogPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const layer = readDataLayer(searchParams.get('layer'));
  const query = searchParams.get('q') ?? '';
  const catalogQuery = useFullLogicalCatalog({
    kind: 'dataset',
    layer,
    summary: isRawLike(layer),
    q: query,
  });
  const catalog = catalogQuery.data ?? null;
  const catalogLoading = isLoadingData(catalogQuery);
  const catalogFailed = catalogQuery.data === undefined ? catalogQuery.error : null;

  function detailHref(item: LogicalCatalogItem, resolution?: string | null): string {
    const detailParams = buildCatalogDetailParams(searchParams, item, layer, resolution);
    if (isRawLike(layer)) {
      detailParams.delete('q');
      if (query) detailParams.set('overviewQ', query);
    }
    return `/catalog/view?${detailParams.toString()}`;
  }

  function overviewContent() {
    return <DataLakeMap />;
  }

  return (
    <div className="catalog-terminal-page">
      {catalogFailed ? <PageHeader title="Data" subtitle="Catalog unavailable" /> : null}
      <div className="catalog-terminal-query">
        {catalogFailed ? (
          <ErrorPanel message={catalogFailed.message} onRetry={() => void catalogQuery.refetch()} />
        ) : (
          <LogicalCatalogWorkspace
            title="Data"
            subtitle="Select a dataset to inspect its table, chart, and features"
            rootLabel="db/data"
            catalog={catalog}
            stats={null}
            catalogKind="dataset"
            isLoading={catalogLoading}
            overview={overviewContent()}
            onItemSelect={(item, resolution) => navigate(detailHref(item, resolution))}
            selectFirstItem={false}
          />
        )}
      </div>
    </div>
  );
}
