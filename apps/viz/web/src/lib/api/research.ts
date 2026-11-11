/**
 * packages/research over the API: sandbox packages, the research docs tree, the corpus
 * wiki and sources, and any markdown document under packages/research.
 *
 * USAGE:
 *   const { data } = useResearchPackages();          // Sandbox
 *   const { data: docs } = useResearchDocs();         // Research
 *   const { data: wiki } = useCorpusWiki();           // Corpus wiki notes and links
 *   const { data: sources } = useCorpusSources();     // Corpus works
 *   const { data: hits } = useCorpusSearch('kelly');  // Full-text search over the sources
 *   const { data: doc } = useResearchDoc('corpus/wiki/topic.md');
 *   researchDocRoute('corpus/wiki/topic.md');        // '/corpus/wiki/topic.md'
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { requestParsed } from './client';
import { type DocPage, docPageSchema } from './docs';
import { encodePath } from './paths';
import { STALE } from './stale-times';

// --------------------------------------------------------------------------- #
// Schemas and types
// --------------------------------------------------------------------------- #

const selectedRunSchema = z
  .object({
    run_id: z.string(),
    run_path: z.string(),
    has_events: z.boolean(),
    has_outcomes: z.boolean(),
    has_verdict: z.boolean(),
  })
  .nullable();

const researchColumnSchema = z.object({
  name: z.string(),
  dtype: z.string(),
});

export const researchDbFileSchema = z.object({
  name: z.string(),
  is_dir: z.boolean(),
  size: z.number().nullable().optional(),
  modified: z.number().optional(),
  type: z.string(),
  row_count: z.number().nullable().optional(),
  columns: z.array(researchColumnSchema).optional(),
});

export const researchPackageSchema = z.object({
  id: z.string(),
  title: z.string(),
  subtitle: z.string(),
  route: z.string(),
  nav_path: z.array(z.string()).optional(),
  surface: z.string().optional(),
  candidate: z.string().optional(),
  memory_version: z.string().optional(),
  session_kind: z.string().optional(),
  disclaimer: z.string().optional(),
  composite_available: z.boolean().optional(),
  session_count: z.number().optional(),
  session_start: z.string().nullable().optional(),
  session_end: z.string().nullable().optional(),
  selected_run: selectedRunSchema.optional(),
  artifact_root_exists: z.boolean().optional(),
  package_path: z.string().optional(),
  package_exists: z.boolean().optional(),
  db_path: z.string().optional(),
  db_available: z.boolean().optional(),
  file_count: z.number().optional(),
  files: z.array(researchDbFileSchema).optional(),
});

export type ResearchNavNode = {
  id: string;
  title: string;
  kind: 'folder' | 'package' | 'doc';
  route?: string;
  doc_path?: string | null;
  subtitle?: string | null;
  surface?: string | null;
  children?: ResearchNavNode[];
};

const researchNavNodeSchema: z.ZodType<ResearchNavNode> = z.lazy(() =>
  z.object({
    id: z.string(),
    title: z.string(),
    kind: z.enum(['folder', 'package', 'doc']),
    route: z.string().optional(),
    doc_path: z.string().nullable().optional(),
    subtitle: z.string().nullable().optional(),
    surface: z.string().nullable().optional(),
    children: z.array(researchNavNodeSchema).optional(),
  }),
);

export const researchPackagesResponseSchema = z.object({
  packages: z.array(researchPackageSchema),
  nav: z.array(researchNavNodeSchema).default([]),
  disclaimer: z.string(),
});

export type ResearchPackage = z.infer<typeof researchPackageSchema>;

export const researchDocsResponseSchema = z.object({
  nav: z.array(researchNavNodeSchema),
});

export const corpusWikiNoteSchema = z.object({
  /** Corpus-relative, e.g. 'wiki/topic/note.md'. */
  path: z.string(),
  title: z.string(),
  /** Frontmatter summary, else the note's opening paragraph. */
  summary: z.string(),
  /** Wiki folder below wiki/ ('' at the root). */
  folder: z.string(),
  /** Wiki notes this note links to. */
  links: z.array(z.string()),
  /** Works this note cites, e.g. 'sources/books/Name'. */
  sources: z.array(z.string()),
});

export const corpusWikiResponseSchema = z.object({ notes: z.array(corpusWikiNoteSchema) });

export const corpusWorkSchema = z.object({
  kind: z.string(),
  name: z.string(),
  /** Corpus-relative work folder, e.g. 'sources/books/Name'. */
  path: z.string(),
  title: z.string(),
  authors: z.array(z.string()),
  year: z.number().nullable(),
  category: z.string().nullable(),
  topics: z.array(z.string()),
  /** Corpus-relative full-text markdown, when extracted. */
  text: z.string().nullable(),
  chapters: z.array(z.object({ path: z.string(), title: z.string() })),
  compressed: z.boolean(),
});

export const corpusSourcesResponseSchema = z.object({ works: z.array(corpusWorkSchema) });

export const corpusSearchResponseSchema = z.object({
  query: z.string(),
  /** Matching texts, of which `results` holds the best. */
  total: z.number(),
  /** Every match's path, and the work path of each matching chapter. */
  matched: z.array(z.string()),
  results: z.array(
    z.object({
      /** Corpus-relative wiki note, chapter or full-text markdown. */
      path: z.string(),
      title: z.string(),
      /** Corpus-relative work folder a chapter belongs to; null for a wiki note. */
      work: z.string().nullable(),
      /** Text around the match; each match sits between U+0002 and U+0003. */
      snippet: z.string(),
    }),
  ),
});

export type CorpusWikiNote = z.infer<typeof corpusWikiNoteSchema>;
export type CorpusWork = z.infer<typeof corpusWorkSchema>;
export type CorpusSearchResponse = z.infer<typeof corpusSearchResponseSchema>;

// --------------------------------------------------------------------------- #
// Routes
// --------------------------------------------------------------------------- #

/** The Viz route that reads a packages/research-relative markdown path. */
export function researchDocRoute(path: string): string {
  const encoded = encodePath(path);
  if (path.startsWith('corpus/')) return `/${encoded}`;
  if (path.startsWith('docs/')) return `/research/doc/${encoded}`;
  return `/sandbox/doc/${encoded}`;
}

// --------------------------------------------------------------------------- #
// Fetchers
// --------------------------------------------------------------------------- #

export async function getResearchPackages(
  signal?: AbortSignal,
): Promise<z.infer<typeof researchPackagesResponseSchema>> {
  return requestParsed('/api/research/packages', researchPackagesResponseSchema, { signal });
}

export async function getResearchDocs(
  signal?: AbortSignal,
): Promise<z.infer<typeof researchDocsResponseSchema>> {
  return requestParsed('/api/research/docs', researchDocsResponseSchema, { signal });
}

export async function getCorpusWiki(
  signal?: AbortSignal,
): Promise<z.infer<typeof corpusWikiResponseSchema>> {
  return requestParsed('/api/research/corpus/wiki', corpusWikiResponseSchema, { signal });
}

export async function getCorpusSources(
  signal?: AbortSignal,
): Promise<z.infer<typeof corpusSourcesResponseSchema>> {
  return requestParsed('/api/research/corpus/sources', corpusSourcesResponseSchema, { signal });
}

export async function getCorpusSearch(
  query: string,
  signal?: AbortSignal,
): Promise<CorpusSearchResponse> {
  const params = new URLSearchParams({ q: query });
  return requestParsed(`/api/research/corpus/search?${params}`, corpusSearchResponseSchema, {
    signal,
  });
}

/** Read one markdown file under packages/research (docs / corpus / sandbox / source). */
export async function getResearchDoc(path: string, signal?: AbortSignal): Promise<DocPage> {
  // Catch-all path: requestParsed avoids openapi-fetch over-encoding.
  return requestParsed(`/api/research/doc/${encodePath(path)}`, docPageSchema, { signal });
}

// --------------------------------------------------------------------------- #
// Hooks
// --------------------------------------------------------------------------- #

export function useResearchPackages() {
  return useQuery({
    queryKey: ['research', 'packages'],
    queryFn: ({ signal }) => getResearchPackages(signal),
    staleTime: STALE.list,
  });
}

export function useResearchDoc(path: string) {
  return useQuery({
    queryKey: ['research', 'doc', path],
    queryFn: ({ signal }) => getResearchDoc(path, signal),
    // Docs are repo files served read-only; matches the docs-tree catalog tier.
    staleTime: STALE.catalog,
    enabled: Boolean(path),
  });
}

export function useResearchDocs() {
  return useQuery({
    queryKey: ['research', 'docs'],
    queryFn: ({ signal }) => getResearchDocs(signal),
    staleTime: STALE.catalog,
  });
}

export function useCorpusWiki() {
  return useQuery({
    queryKey: ['research', 'corpus', 'wiki'],
    queryFn: ({ signal }) => getCorpusWiki(signal),
    staleTime: STALE.catalog,
  });
}

export function useCorpusSources() {
  return useQuery({
    queryKey: ['research', 'corpus', 'sources'],
    queryFn: ({ signal }) => getCorpusSources(signal),
    staleTime: STALE.catalog,
  });
}

export function useCorpusSearch(query: string) {
  const trimmed = query.trim();
  return useQuery({
    queryKey: ['research', 'corpus', 'search', trimmed],
    queryFn: ({ signal }) => getCorpusSearch(trimmed, signal),
    staleTime: STALE.catalog,
    enabled: trimmed.length > 0,
    placeholderData: (previous) => previous,
  });
}
