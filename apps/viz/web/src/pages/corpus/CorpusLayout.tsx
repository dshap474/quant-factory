/**
 * Corpus workspace layout: one navigator with the works by kind under Sources and the wiki
 * folder tree under Wiki, beside the routed corpus pages. The title leads to the wiki graph.
 * The search box above the tree searches the wiki and every source's full text: the tree
 * narrows to the matching works, chapters and notes as you type, and the query rides in
 * the URL (?q=) so the opened page marks it and the wiki page lists the ranked matches.
 *
 * USAGE:
 *   Declared as the parent route for /corpus/*.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useMemo, useState } from 'react';
import { useCorpusSearch, useCorpusSources, useCorpusWiki } from '@/lib/api/research';
import { isLoadingData, SectionLayout, useDebouncedCallback, useSearchParamState } from '@/ui';
import { ResearchTreeNavigator } from '../research/ResearchTreeNavigator';
import { sourcesNav, wikiNav } from './corpus-model';

// --------------------------------------------------------------------------- #
// Layout
// --------------------------------------------------------------------------- #

const SEARCH_DEBOUNCE_MS = 250;

function CorpusNavigator() {
  const wiki = useCorpusWiki();
  const works = useCorpusSources();
  // The URL holds the query, so a search can be shared and survives back and forward.
  const [query, setQuery] = useSearchParamState('q', '', { replace: true });
  const [draft, setDraft] = useState(query);
  const [seen, setSeen] = useState(query);
  // A link without the query (or back to one with another) replaces what was typed.
  if (query !== seen) {
    setSeen(query);
    if (query !== draft.trim()) setDraft(query);
  }
  const commit = useDebouncedCallback(setQuery, SEARCH_DEBOUNCE_MS);
  const search = useCorpusSearch(query);
  const matched = search.data?.matched;
  const matches = useMemo(() => new Set(matched), [matched]);
  return (
    <ResearchTreeNavigator
      title="Corpus"
      home="/corpus/wiki"
      sections={[
        {
          id: 'sources',
          label: 'Sources',
          home: '/corpus/sources',
          nav: sourcesNav(works.data?.works ?? []),
        },
        {
          id: 'wiki',
          label: 'Wiki',
          home: '/corpus/wiki',
          nav: wikiNav(wiki.data?.notes ?? []),
        },
      ]}
      loading={isLoadingData(works) || isLoadingData(wiki)}
      error={
        (works.data === undefined ? works.error?.message : undefined) ??
        (wiki.data === undefined ? wiki.error?.message : undefined) ??
        null
      }
      noun="sources or notes"
      search={{
        value: draft,
        onChange: (value) => {
          setDraft(value);
          commit(value.trim());
        },
        placeholder: 'Search wiki and sources',
        matches: query ? matches : undefined,
        linkSearch: query ? `?${new URLSearchParams({ q: query })}` : '',
      }}
    />
  );
}

export function CorpusLayout() {
  return <SectionLayout navigator={<CorpusNavigator />} />;
}
