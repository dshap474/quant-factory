/**
 * Corpus sources: every book, paper and reference by kind, under the corpus search; one work in the reading frame with
 * its contents and the wiki notes that cite it; or a chapter or full text in the reader, with
 * its work, its place in the work and links to the chapters either side.
 *
 * USAGE:
 *   Routed at /corpus/sources, /corpus/sources/<kind>/<Name> and /corpus/sources/<...>.md
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { useParams } from 'react-router';
import { type CorpusWork, useCorpusSources, useCorpusWiki } from '@/lib/api/research';
import {
  Badge,
  Cluster,
  EmptyState,
  ErrorPanel,
  isLoadingData,
  Link,
  LoadingSkeleton,
  PageHeader,
  Prose,
  Reader,
  ReaderLinkList,
  type ReaderMetaItem,
  type ReaderSection,
  Section,
  Stack,
  Text,
  useSearchParamState,
} from '@/ui';
import { ResearchReader } from '../research/ResearchReader';
import { CorpusSearch } from './CorpusSearch';
import { backlinks, corpusRoute, kindName, kindTitle, noteRoute } from './corpus-model';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

/** A book's index (a heading ending in "Index") reads as columns of entries. */
const BACK_INDEX = /\bindex\W*$/i;

function byline(work: CorpusWork): string {
  return [work.authors.join(', '), work.year].filter(Boolean).join(' · ');
}

function WorkRow({ work }: { work: CorpusWork }) {
  return (
    <Stack gap="none">
      <Cluster gap="stack">
        <Link to={corpusRoute(work.path)}>{work.title}</Link>
        {work.category ? <Badge size="sm">{work.category}</Badge> : null}
      </Cluster>
      <Text variant="caption" tone="muted">
        {[byline(work), `${work.chapters.length} chapters`].filter(Boolean).join(' · ')}
      </Text>
    </Stack>
  );
}

// --------------------------------------------------------------------------- #
// Pages
// --------------------------------------------------------------------------- #

function SourcesIndex({ works }: { works: readonly CorpusWork[] }) {
  return (
    <CorpusSearch works={works}>
      <WorkList works={works} />
    </CorpusSearch>
  );
}

function WorkList({ works }: { works: readonly CorpusWork[] }) {
  const kinds = [...new Set(works.map((work) => work.kind))].sort();
  return (
    <Stack gap="section">
      {kinds.map((kind) => {
        const rows = works
          .filter((work) => work.kind === kind)
          .sort((a, b) => a.title.localeCompare(b.title));
        return (
          <Section key={kind} title={`${kindTitle(kind)} (${rows.length})`}>
            <Stack gap="heading">
              {rows.map((work) => (
                <WorkRow key={work.path} work={work} />
              ))}
            </Stack>
          </Section>
        );
      })}
    </Stack>
  );
}

const WORK_SECTIONS: ReaderSection[] = [
  { id: 'contents', label: 'Contents' },
  { id: 'cited-by', label: 'Cited by' },
];

/** One work in the reading frame: its facts, its chapters and the notes that cite it. */
function WorkDetail({ work }: { work: CorpusWork }) {
  const wiki = useCorpusWiki();
  const citing = backlinks(wiki.data?.notes ?? [], work.path);
  const meta: ReaderMetaItem[] = [
    { label: 'Kind', value: kindName(work.kind) },
    ...(work.year ? [{ label: 'Year', value: String(work.year) }] : []),
    ...(work.category ? [{ label: 'Category', value: work.category }] : []),
    ...(work.topics.length ? [{ label: 'Topics', value: work.topics.join(', ') }] : []),
    ...(work.text
      ? [{ label: 'Full text', value: <Link to={corpusRoute(work.text)}>Read</Link> }]
      : []),
  ];
  return (
    <Reader
      title={work.title}
      lede={byline(work) || undefined}
      meta={meta}
      sections={citing.length ? WORK_SECTIONS : WORK_SECTIONS.slice(0, 1)}
    >
      <Prose as="div">
        <ReaderLinkList
          id="contents"
          title="Contents"
          items={work.chapters.map((chapter) => ({
            label: chapter.title,
            to: corpusRoute(chapter.path),
          }))}
          empty="No chapters split out."
        />
        {citing.length ? (
          <ReaderLinkList
            id="cited-by"
            title="Cited by"
            items={citing.map((note) => ({ label: note.title, to: noteRoute(note.path) }))}
          />
        ) : null}
      </Prose>
    </Reader>
  );
}

/** A chapter or full text in the reader, placed in its work, with the chapters either side. */
function SourceText({ path, work }: { path: string; work: CorpusWork | undefined }) {
  // Opened from a search result: the search's words are marked in the text.
  const [query] = useSearchParamState('q', '');
  // Paging keeps the search, so the navigator stays narrowed and the next chapter marked.
  const carry = query ? `?${new URLSearchParams({ q: query })}` : '';
  const chapters = work?.chapters ?? [];
  const index = chapters.findIndex((chapter) => chapter.path === path);
  const chapter = chapters[index];
  const previous = index > 0 ? chapters[index - 1] : undefined;
  const next = index >= 0 ? chapters[index + 1] : undefined;
  const meta: ReaderMetaItem[] = work
    ? [
        { label: 'Work', value: <Link to={corpusRoute(work.path)}>{work.title}</Link> },
        index >= 0
          ? { label: 'Part', value: `${index + 1} of ${chapters.length}` }
          : { label: 'Part', value: 'Full text' },
      ]
    : [];
  return (
    <ResearchReader
      docPath={`corpus/${path}`}
      lede={work ? byline(work) : undefined}
      meta={meta}
      layout={chapter && BACK_INDEX.test(chapter.title) ? 'index' : 'flow'}
      highlight={query || undefined}
      pager={{
        label: 'Chapters',
        previous: previous
          ? { label: previous.title, to: `${corpusRoute(previous.path)}${carry}` }
          : undefined,
        next: next ? { label: next.title, to: `${corpusRoute(next.path)}${carry}` } : undefined,
      }}
    />
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function CorpusSourcesPage() {
  const splat = useParams()['*'] ?? '';
  const sources = useCorpusSources();
  const works = sources.data?.works ?? [];
  const path = `sources/${splat}`;
  const text = /\.md$/i.test(splat);
  const work = splat
    ? works.find((item) => (text ? path.startsWith(`${item.path}/`) : item.path === path))
    : undefined;
  const sourcesLoading = isLoadingData(sources);
  const header = (
    <PageHeader
      title="Sources"
      subtitle={
        sourcesLoading ? (
          <LoadingSkeleton variant="line" announce={false} className="w-24" />
        ) : (
          `${works.length} works`
        )
      }
    />
  );

  let body: ReactNode;
  if (text) body = <SourceText key={path} path={path} work={work} />;
  else if (sourcesLoading) body = <LoadingSkeleton count={8} />;
  else if (sources.error && !sources.data)
    body = <ErrorPanel message={sources.error.message} onRetry={() => void sources.refetch()} />;
  else if (work) body = <WorkDetail work={work} />;
  else if (splat)
    body = <EmptyState title="Source not found" hint={`No work at sources/${splat}.`} />;
  else if (works.length === 0)
    body = <EmptyState title="No sources" hint="The corpus has no works on this machine." />;
  else body = <SourcesIndex works={works} />;

  return (
    <>
      {header}
      {body}
    </>
  );
}
