/**
 * Corpus wiki: every note and cited work as one graph (or, while the navigator searches,
 * the ranked matches), or one note in the reader with what links to it. Selecting a node
 * in the graph shows the note's summary beside it; the navigator's title leads back.
 *
 * USAGE:
 *   Routed at /corpus/wiki (graph) and /corpus/wiki/<note>.md (?view=graph keeps the graph;
 *   ?q= marks a search's words in the note).
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { NetworkGraph } from '@quant-factory/qf-ui/charts/network';
import { ArrowRight, X } from 'lucide-react';
import { useMemo } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router';
import { type CorpusWikiNote, useCorpusSources, useCorpusWiki } from '@/lib/api/research';
import {
  Badge,
  Cluster,
  Columns,
  EmptyState,
  ErrorPanel,
  isLoadingData,
  Link,
  LoadingSkeleton,
  PageHeader,
  pluralize,
  Section,
  Stack,
  Surface,
  Text,
} from '@/ui';
import { ResearchReader } from '../research/ResearchReader';
import { CorpusSearch } from './CorpusSearch';
import { backlinks, corpusRoute, noteRoute, wikiGraph } from './corpus-model';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

type WikiView = 'graph' | 'reader';

function folderLabel(folder: string): string {
  return folder.split('/').join(' / ') || 'wiki';
}

function NoteLinks({ title, notes }: { title: string; notes: readonly CorpusWikiNote[] }) {
  if (notes.length === 0) return null;
  return (
    <Section title={`${title} (${notes.length})`}>
      <Cluster gap="stack">
        {notes.map((note) => (
          <Link key={note.path} to={noteRoute(note.path)}>
            {note.title}
          </Link>
        ))}
      </Cluster>
    </Section>
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function CorpusWikiPage() {
  const splat = useParams()['*'] ?? '';
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const wiki = useCorpusWiki();
  const sources = useCorpusSources();
  const notes = wiki.data?.notes ?? [];
  const works = sources.data?.works ?? [];
  const graph = useMemo(
    () => wikiGraph(wiki.data?.notes ?? [], sources.data?.works ?? []),
    [wiki.data, sources.data],
  );

  const notePath = splat ? `wiki/${decodeURIComponent(splat)}` : null;
  const note = notes.find((item) => item.path === notePath);
  const view: WikiView = !notePath || search.get('view') === 'graph' ? 'graph' : 'reader';

  const select = (id: string | null) => {
    if (!id) navigate('/corpus/wiki');
    else if (id.startsWith('wiki/')) navigate(`${noteRoute(id)}?view=graph`);
    else navigate(corpusRoute(id));
  };

  const wikiLoading = isLoadingData(wiki);
  const header = (
    <PageHeader
      title="Wiki"
      subtitle={
        wikiLoading || isLoadingData(sources) ? (
          <LoadingSkeleton variant="line" announce={false} className="w-40" />
        ) : (
          `${notes.length} notes · ${graph.links.length} links`
        )
      }
    />
  );

  if (wikiLoading) {
    return (
      <>
        {header}
        <LoadingSkeleton count={8} />
      </>
    );
  }
  if (wiki.error && !wiki.data) {
    return (
      <>
        {header}
        <ErrorPanel message={wiki.error.message} onRetry={() => void wiki.refetch()} />
      </>
    );
  }
  if (notes.length === 0) {
    return (
      <>
        {header}
        <EmptyState title="No wiki notes" hint="The corpus wiki is empty on this machine." />
      </>
    );
  }

  if (view === 'reader' && notePath) {
    const linksTo = notes.filter((item) => note?.links.includes(item.path));
    const cited = works.filter((work) => note?.sources.includes(work.path));
    const linkedFrom = backlinks(notes, notePath).length;
    return (
      <>
        {header}
        <ResearchReader
          docPath={`corpus/${notePath}`}
          highlight={search.get('q') || undefined}
          meta={
            note
              ? [
                  { label: 'Topic', value: folderLabel(note.folder) },
                  ...(cited.length > 0
                    ? [
                        {
                          label: 'Cites',
                          value: `${cited.length} ${pluralize(cited.length, 'work')}`,
                        },
                      ]
                    : []),
                  {
                    label: 'Linked from',
                    value: `${linkedFrom} ${pluralize(linkedFrom, 'note')}`,
                  },
                ]
              : []
          }
        >
          <Stack gap="section">
            {cited.length > 0 ? (
              <Section title={`Cites (${cited.length})`}>
                <Cluster gap="stack">
                  {cited.map((work) => (
                    <Link key={work.path} to={corpusRoute(work.path)}>
                      {work.title}
                    </Link>
                  ))}
                </Cluster>
              </Section>
            ) : null}
            <NoteLinks title="Links to" notes={linksTo} />
            <NoteLinks title="Linked from" notes={backlinks(notes, notePath)} />
          </Stack>
        </ResearchReader>
      </>
    );
  }

  // The wrapper takes the column's full height so the summary card keeps its own.
  const inspector = notePath ? (
    <div>
      <Surface as="aside" padding="md" aria-label="Note summary">
        <Stack gap="heading">
          <Cluster justify="between" align="start" wrap={false}>
            <Stack gap="xs">
              <Text variant="eyebrow" tone="muted">
                {note ? folderLabel(note.folder) : 'wiki'}
              </Text>
              <Text weight="semibold">{note?.title ?? notePath}</Text>
            </Stack>
            <Link to="/corpus/wiki" variant="control" size="sm" icon aria-label="Close note">
              <X aria-hidden="true" size={14} />
            </Link>
          </Cluster>
          {note?.summary ? <Text tone="muted">{note.summary}</Text> : null}
          <Cluster gap="stack">
            <Badge size="sm">{backlinks(notes, notePath).length} backlinks</Badge>
            <Badge size="sm">{note?.links.length ?? 0} links</Badge>
            <Badge size="sm">{note?.sources.length ?? 0} sources</Badge>
          </Cluster>
          <Link to={noteRoute(notePath)} variant="control" size="sm">
            Read note
            <ArrowRight aria-hidden="true" size={14} />
          </Link>
        </Stack>
      </Surface>
    </div>
  ) : null;

  const graphView = (
    <Columns template={inspector ? 'minmax(0,1fr) minmax(0,22rem)' : 'minmax(0,1fr)'} from="lg">
      <NetworkGraph
        label="Corpus wiki notes, their links and cited sources"
        nodes={graph.nodes}
        links={graph.links}
        selectedId={notePath}
        onSelect={select}
        peers={false}
        height="calc(100vh - 12rem)"
        legend={[
          ...graph.folders.map((folder, index) => ({
            series: index + 1,
            label: folder || 'wiki',
          })),
          { label: 'source', tone: 'neutral' },
        ]}
      />
      {inspector}
    </Columns>
  );

  // A search (typed in the navigator) lists its matches on the front page in the graph's place.
  return (
    <>
      {header}
      {notePath ? graphView : <CorpusSearch works={works}>{graphView}</CorpusSearch>}
    </>
  );
}
