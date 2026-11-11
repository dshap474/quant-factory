/**
 * Docs API — documentation tree and pages.
 *
 * USAGE:
 *   const { data: tree } = useDocsTree();
 *   const { data: page } = useDocPage('packages/data');
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { getParsed, requestParsed } from './client';
import { encodePath } from './paths';
import { STALE } from './stale-times';

// --------------------------------------------------------------------------- #
// Schema
// --------------------------------------------------------------------------- #

export type DocsNode = {
  type: 'dir' | 'file';
  path: string;
  title: string;
  generated?: boolean;
  children?: DocsNode[];
};

const docsNodeSchema: z.ZodType<DocsNode> = z.lazy(() =>
  z.object({
    type: z.enum(['dir', 'file']),
    path: z.string(),
    title: z.string(),
    generated: z.boolean().optional(),
    children: z.array(docsNodeSchema).optional(),
  }),
);

export const docsTreeSchema = z.object({
  root: docsNodeSchema,
  default_path: z.string().nullable(),
});

export const docPageSchema = z.object({
  path: z.string(),
  title: z.string(),
  markdown: z.string(),
  modified: z.number().nullable(),
  generated: z.boolean(),
});

export type DocsTree = z.infer<typeof docsTreeSchema>;
export type DocPage = z.infer<typeof docPageSchema>;

// --------------------------------------------------------------------------- #
// Fetch
// --------------------------------------------------------------------------- #

export async function getDocsTree(signal?: AbortSignal): Promise<DocsTree> {
  return getParsed('/api/docs/tree', docsTreeSchema, { signal });
}

export async function getDocPage(path: string, signal?: AbortSignal): Promise<DocPage> {
  // Catch-all path: requestParsed avoids openapi-fetch over-encoding.
  return requestParsed(`/api/docs/page/${encodePath(path)}`, docPageSchema, { signal });
}

// --------------------------------------------------------------------------- #
// Hooks
// --------------------------------------------------------------------------- #

export const docsKeys = {
  all: ['docs'] as const,
  tree: () => [...docsKeys.all, 'tree'] as const,
  page: (path: string) => [...docsKeys.all, 'page', path] as const,
};

export function useDocsTree() {
  return useQuery({
    queryKey: docsKeys.tree(),
    queryFn: ({ signal }) => getDocsTree(signal),
    staleTime: STALE.catalog,
  });
}

export function useDocPage(path: string) {
  return useQuery({
    queryKey: docsKeys.page(path),
    queryFn: ({ signal }) => getDocPage(path, signal),
    // Repo docs change on the docs-tree cadence; share the catalog tier.
    staleTime: STALE.catalog,
    enabled: Boolean(path),
  });
}
