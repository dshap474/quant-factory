/**
 * Features catalog route — pipeline overview until a feature set is selected.
 *
 * USAGE:
 *   Routed at /features
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useSearchParams } from 'react-router';

import { useLogicalCatalog } from '@/lib/api/catalog';
import { useFeatureBrowserStats } from '@/lib/api/features';
import { LogicalCatalogWorkspace } from '@/lib/components/LogicalCatalogWorkspace';
import { ErrorPanel, isLoadingData, PageHeader, PipelineArchitectureMap } from '@/ui';

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function FeaturesPage() {
  const [searchParams] = useSearchParams();
  const catalogPage = Math.max(1, Number(searchParams.get('catalogPage')) || 1);
  const catalogQuery = useLogicalCatalog({
    kind: 'feature_set',
    layer: 'features',
    domain: searchParams.get('domain'),
    q: searchParams.get('q') ?? '',
    offset: (catalogPage - 1) * 100,
    limit: 100,
  });
  const statsQuery = useFeatureBrowserStats();
  const catalogLoading = isLoadingData(catalogQuery);
  // The workspace owns its loading skeletons (its controls stay mounted); only a
  // failure with nothing to show replaces it.
  const failed =
    (catalogQuery.data === undefined ? catalogQuery.error : null) ??
    (statsQuery.data === undefined ? statsQuery.error : null);

  return (
    <div className="catalog-terminal-page">
      {failed ? <PageHeader title="Features" subtitle="Feature catalog unavailable" /> : null}
      <div className="catalog-terminal-query">
        {failed ? (
          <ErrorPanel
            message={failed.message}
            onRetry={() => {
              void catalogQuery.refetch();
              void statsQuery.refetch();
            }}
          />
        ) : (
          <LogicalCatalogWorkspace
            title="Features"
            subtitle="Select a feature set to inspect its table, chart, correlation, and IC matrix"
            rootLabel="db/features"
            catalog={catalogQuery.data ?? null}
            stats={statsQuery.data ?? null}
            catalogKind="feature_set"
            isLoading={catalogLoading}
            overview={
              searchParams.get('item') ? undefined : (
                <PipelineArchitectureMap scope="features" hideHeader />
              )
            }
            selectFirstItem={false}
          />
        )}
      </div>
    </div>
  );
}
