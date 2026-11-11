/**
 * Corpus search results: with a query in the URL (?q=, typed in the navigator's search box)
 * it shows the ranked wiki notes and source chapters; without one, the page's own content.
 *
 * USAGE:
 *   <CorpusSearch works={works}><WorkList works={works} /></CorpusSearch>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { type CorpusWork, useCorpusSearch } from '@/lib/api/research';
import {
  Cluster,
  EmptyState,
  ErrorPanel,
  HighlightedText,
  isLoadingData,
  Link,
  LoadingSkeleton,
  pluralize,
  Stack,
  Text,
  useSearchParamState,
} from '@/ui';
import { corpusRoute } from './corpus-model';

// --------------------------------------------------------------------------- #
// Results
// --------------------------------------------------------------------------- #

/** Ranked wiki notes and chapters matching the query, each with its matching passage. */
function SearchResults({ query, works }: { query: string; works: readonly CorpusWork[] }) {
  const search = useCorpusSearch(query);
  // Placeholder results belong to the previous query: skeleton them, never paint them.
  if (isLoadingData(search)) return <LoadingSkeleton count={6} />;
  if (search.error && !search.data)
    return <ErrorPanel message={search.error.message} onRetry={() => void search.refetch()} />;
  if (!search.data) return <EmptyState title="Type to search the corpus" />;
  const { total, results } = search.data;
  if (results.length === 0)
    return (
      <EmptyState
        title="No matches"
        hint={`Nothing in the wiki or the sources matches “${query}”.`}
      />
    );
  const workTitles = new Map(works.map((work) => [work.path, work.title]));
  return (
    <Stack gap="section">
      <Text as="h2" variant="label">
        {total > results.length
          ? `Best ${results.length} of ${total} matches`
          : `${total} ${pluralize(total, 'match', 'matches')}`}
      </Text>
      {results.map((hit) => (
        <Stack key={hit.path} gap="none">
          <Cluster gap="stack">
            <Link to={`${corpusRoute(hit.path)}?${new URLSearchParams({ q: query })}`}>
              {hit.title}
            </Link>
            <Text variant="caption" tone="muted">
              {hit.work === null ? 'Wiki note' : (workTitles.get(hit.work) ?? hit.work)}
            </Text>
          </Cluster>
          <Text tone="muted">
            <HighlightedText text={hit.snippet} />
          </Text>
        </Stack>
      ))}
    </Stack>
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function CorpusSearch({
  works,
  children,
}: {
  /** Source works, to name the work each chapter belongs to. */
  works: readonly CorpusWork[];
  /** Shown while there is no query. */
  children: ReactNode;
}) {
  const [query] = useSearchParamState('q', '');
  return query ? <SearchResults query={query} works={works} /> : children;
}
