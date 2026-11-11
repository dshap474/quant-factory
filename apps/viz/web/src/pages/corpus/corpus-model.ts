/**
 * Corpus view model: routes, navigator trees, graph nodes and backlinks built from the
 * corpus wiki and sources indexes.
 *
 * USAGE:
 *   noteRoute('wiki/factors/momentum.md');        // '/corpus/wiki/factors/momentum.md'
 *   workRoute('sources/books/Name');               // '/corpus/sources/books/Name'
 *   wikiNav(notes); sourcesNav(works); wikiGraph(notes); backlinks(notes, path)
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { NetworkGraphLink, NetworkGraphNode } from '@quant-factory/qf-ui/charts/network';
import { encodePath } from '@/lib/api/paths';
import type { CorpusWikiNote, CorpusWork, ResearchNavNode } from '@/lib/api/research';

// --------------------------------------------------------------------------- #
// Routes
// --------------------------------------------------------------------------- #

/** A corpus-relative path ('wiki/...md', 'sources/<kind>/<Name>[/...]') as a Viz route. */
export function corpusRoute(path: string): string {
  return `/corpus/${encodePath(path)}`;
}

export const noteRoute = corpusRoute;
export const workRoute = corpusRoute;

const KIND_TITLES: Record<string, string> = {
  book: 'Books',
  paper: 'Papers',
  reference: 'References',
};

const KIND_NAMES: Record<string, string> = {
  book: 'Book',
  paper: 'Paper',
  reference: 'Reference',
};

export function kindTitle(kind: string): string {
  return KIND_TITLES[kind] ?? kind;
}

/** One work's kind: "Book", where `kindTitle` names the group ("Books"). */
export function kindName(kind: string): string {
  return KIND_NAMES[kind] ?? kind;
}

function folderTitle(folder: string): string {
  return folder.replace(/[-_]/g, ' ').replace(/^\w/, (letter) => letter.toUpperCase());
}

// --------------------------------------------------------------------------- #
// Navigator trees
// --------------------------------------------------------------------------- #

/** Wiki notes under their folders, folders first, each level by title. */
export function wikiNav(notes: readonly CorpusWikiNote[]): ResearchNavNode[] {
  const root: ResearchNavNode[] = [];
  const folders = new Map<string, ResearchNavNode>();
  const folderFor = (folder: string): ResearchNavNode[] => {
    if (!folder) return root;
    const existing = folders.get(folder);
    if (existing) return existing.children ?? [];
    const parts = folder.split('/');
    const node: ResearchNavNode = {
      id: `wiki:${folder}`,
      title: folderTitle(parts.at(-1) ?? folder),
      kind: 'folder',
      children: [],
    };
    folders.set(folder, node);
    folderFor(parts.slice(0, -1).join('/')).push(node);
    return node.children ?? [];
  };
  for (const note of notes) {
    folderFor(note.folder).push({
      id: note.path,
      title: note.title,
      kind: 'doc',
      route: noteRoute(note.path),
      doc_path: `corpus/${note.path}`,
    });
  }
  const sort = (nodes: ResearchNavNode[]) => {
    nodes.sort(
      (a, b) =>
        Number(a.kind !== 'folder') - Number(b.kind !== 'folder') || a.title.localeCompare(b.title),
    );
    for (const node of nodes) if (node.children) sort(node.children);
  };
  sort(root);
  return root;
}

// "Chapter 2: Methods" (or "Chapter 2." / "Chapter 2 —") before a name.
const CHAPTER_PREFIX = /^chapter\s+(\d+)\s*[:.\-\u2013\u2014]?\s+(?=\S)/i;

/** A chapter's sidebar label: "2. Methods", so the name fits the row. */
export function chapterLabel(title: string): string {
  if (CHAPTER_PREFIX.test(title)) return title.replace(CHAPTER_PREFIX, '$1. ');
  return title.replace(/^CHAPTER\b/, 'Chapter');
}

/** Works under their kind (Books, Papers, References), each by title, with its chapters in order. */
export function sourcesNav(works: readonly CorpusWork[]): ResearchNavNode[] {
  const kinds = [...new Set(works.map((work) => work.kind))].sort();
  return kinds.map((kind) => ({
    id: `sources:${kind}`,
    title: kindTitle(kind),
    kind: 'folder' as const,
    children: works
      .filter((work) => work.kind === kind)
      .sort((a, b) => a.title.localeCompare(b.title))
      .map((work) => ({
        id: work.path,
        title: work.title,
        // A work with chapters opens to them; its row still leads to the work.
        kind: work.chapters.length ? ('folder' as const) : ('doc' as const),
        route: workRoute(work.path),
        subtitle: [work.authors.join(', '), work.year].filter(Boolean).join(' · ') || null,
        children: work.chapters.length
          ? work.chapters.map((chapter) => ({
              id: chapter.path,
              title: chapterLabel(chapter.title),
              kind: 'doc' as const,
              route: corpusRoute(chapter.path),
              // The full title on hover.
              subtitle: chapter.title,
            }))
          : undefined,
      })),
  }));
}

// --------------------------------------------------------------------------- #
// Graph
// --------------------------------------------------------------------------- #

/** Top-level wiki folder, which picks a note's colour. */
export function topFolder(note: CorpusWikiNote): string {
  return note.folder.split('/')[0] ?? '';
}

export interface WikiGraph {
  nodes: NetworkGraphNode[];
  links: NetworkGraphLink[];
  folders: string[];
}

/**
 * Notes as circles sized by how many notes they touch and coloured by top folder; cited
 * works as diamonds sized by how many notes cite them. Links are undirected and deduplicated.
 */
export function wikiGraph(
  notes: readonly CorpusWikiNote[],
  works: readonly CorpusWork[],
): WikiGraph {
  const folders = [...new Set(notes.map(topFolder))].sort();
  const pairs = new Map<string, NetworkGraphLink>();
  const add = (a: string, b: string) => {
    if (a === b) return;
    const [source, target] = a < b ? [a, b] : [b, a];
    pairs.set(`${source}\n${target}`, { source, target });
  };
  for (const note of notes) {
    for (const link of note.links) add(note.path, link);
    for (const source of note.sources) add(note.path, source);
  }
  const links = [...pairs.values()];
  const degree = new Map<string, number>();
  for (const { source, target } of links) {
    degree.set(source, (degree.get(source) ?? 0) + 1);
    degree.set(target, (degree.get(target) ?? 0) + 1);
  }
  const titles = new Map(works.map((work) => [work.path, work.title]));
  const cited = [...new Set(notes.flatMap((note) => note.sources))].sort();
  const nodes: NetworkGraphNode[] = [
    ...notes.map((note) => ({
      id: note.path,
      label: note.title,
      weight: degree.get(note.path) ?? 1,
      series: folders.indexOf(topFolder(note)) + 1,
      title: `${note.title} · ${note.folder || 'wiki'}`,
    })),
    ...cited.map((path) => ({
      id: path,
      label: titles.get(path) ?? path.split('/').at(-1) ?? path,
      kind: 'secondary' as const,
      tone: 'neutral' as const,
      weight: degree.get(path) ?? 1,
      title: `${titles.get(path) ?? path} (source)`,
    })),
  ];
  return { nodes, links, folders };
}

// --------------------------------------------------------------------------- #
// Backlinks
// --------------------------------------------------------------------------- #

/** Notes that link to `path`, whether `path` is a note or a cited work. */
export function backlinks(notes: readonly CorpusWikiNote[], path: string): CorpusWikiNote[] {
  return notes
    .filter((note) => note.links.includes(path) || note.sources.includes(path))
    .sort((a, b) => a.title.localeCompare(b.title));
}
