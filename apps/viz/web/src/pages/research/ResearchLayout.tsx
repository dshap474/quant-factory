/**
 * Research workspace layout: the packages/research/docs tree beside the routed reader.
 *
 * USAGE:
 *   Declared as the parent route for /research/*.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useResearchDocs } from '@/lib/api/research';
import { SectionLayout } from '@/ui';
import { ResearchTreeNavigator } from './ResearchTreeNavigator';

// --------------------------------------------------------------------------- #
// Layout
// --------------------------------------------------------------------------- #

function ResearchNavigator() {
  const docs = useResearchDocs();
  return (
    <ResearchTreeNavigator
      title="Research"
      home="/research"
      nav={docs.data?.nav ?? []}
      loading={docs.isLoading}
      error={docs.error?.message ?? null}
      noun="documents"
    />
  );
}

export function ResearchLayout() {
  return <SectionLayout navigator={<ResearchNavigator />} />;
}
