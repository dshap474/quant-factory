/**
 * Physical lake explorer for parquet, Markdown, JSON, and YAML artifacts.
 *
 * USAGE:
 *   <DatasetExplorer scope="features" rootLabel="db/features" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useReducer, useRef } from 'react';
import { type MarkdownPreview, previewMarkdown, type StructuredPreview } from '@/lib/api/catalog';
import { useDatasetListing } from '@/lib/api/dataset-queries';
import { previewFeatureMarkdown, previewFeatureStructured } from '@/lib/api/features';
import {
  Button,
  CodeBlock,
  Columns,
  EmptyState,
  ErrorPanel,
  Input,
  Inset,
  isLoadingData,
  LoadingSkeleton,
  ScrollArea,
  Stack,
  Surface,
  Text,
  Toolbar,
} from '@/ui';

import { DatasetViewer } from './DatasetViewer';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface DatasetExplorerProps {
  scope: 'data' | 'features';
  rootLabel: string;
}

type OpenFile =
  | { kind: 'parquet'; path: string }
  | { kind: 'markdown'; path: string; preview: MarkdownPreview }
  | { kind: 'structured'; path: string; preview: StructuredPreview };

interface ExplorerState {
  path: string;
  openFile: OpenFile | null;
  search: string;
  error: string | null;
  /** The non-parquet file being fetched for preview, or null. */
  opening: string | null;
}

type ExplorerAction =
  | { type: 'patch'; value: Partial<ExplorerState> }
  | { type: 'navigate'; path: string };

const INITIAL_STATE: ExplorerState = {
  path: '',
  openFile: null,
  search: '',
  error: null,
  opening: null,
};

function explorerReducer(state: ExplorerState, action: ExplorerAction): ExplorerState {
  if (action.type === 'navigate') {
    return { ...state, path: action.path, openFile: null, search: '', error: null, opening: null };
  }
  return { ...state, ...action.value };
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function DatasetExplorer({ scope, rootLabel }: DatasetExplorerProps) {
  const [state, dispatch] = useReducer(explorerReducer, INITIAL_STATE);
  const { path, openFile, search, error: openError, opening } = state;
  // The last file open request: it retries a failed open and drops a superseded response.
  const lastOpen = useRef<{ nextPath: string; name: string; type: string } | null>(null);
  const listingQuery = useDatasetListing(scope, path);
  const listing = listingQuery.data ?? null;
  const loading = isLoadingData(listingQuery);
  const listingError =
    listingQuery.error && listingQuery.data === undefined ? listingQuery.error.message : null;
  const error = openError ?? listingError;

  const normalizedSearch = search.trim().toLowerCase();
  const items = normalizedSearch
    ? (listing?.items ?? []).filter((item) =>
        `${item.name} ${item.label ?? ''}`.toLowerCase().includes(normalizedSearch),
      )
    : (listing?.items ?? []);

  function navigate(nextPath: string) {
    lastOpen.current = null;
    dispatch({ type: 'navigate', path: nextPath });
  }

  function openItem(name: string, isDir: boolean, type: string) {
    const nextPath = path ? `${path}/${name}` : name;
    if (isDir) {
      navigate(nextPath);
      return;
    }
    void openFileAt(nextPath, name, type);
  }

  async function openFileAt(nextPath: string, name: string, type: string) {
    const request = { nextPath, name, type };
    lastOpen.current = request;
    const current = () => lastOpen.current === request;
    dispatch({ type: 'patch', value: { error: null, opening: null } });
    if (type === 'parquet' || name.endsWith('.parquet')) {
      dispatch({ type: 'patch', value: { openFile: { kind: 'parquet', path: nextPath } } });
      return;
    }
    const isMarkdown = type === 'markdown' || name.endsWith('.md');
    const isStructured = scope === 'features' && ['json', 'yaml'].includes(type);
    if (!isMarkdown && !isStructured) return;
    dispatch({ type: 'patch', value: { openFile: null, opening: nextPath } });
    try {
      if (isMarkdown) {
        const preview = await (scope === 'features' ? previewFeatureMarkdown : previewMarkdown)(
          nextPath,
        );
        if (!current()) return;
        dispatch({
          type: 'patch',
          value: { openFile: { kind: 'markdown', path: nextPath, preview }, opening: null },
        });
        return;
      }
      const preview = await previewFeatureStructured(nextPath);
      if (!current()) return;
      dispatch({
        type: 'patch',
        value: { openFile: { kind: 'structured', path: nextPath, preview }, opening: null },
      });
    } catch (caught) {
      if (!current()) return;
      dispatch({
        type: 'patch',
        value: {
          error: caught instanceof Error ? caught.message : 'Failed to open artifact',
          opening: null,
        },
      });
    }
  }

  function retry() {
    if (openError && lastOpen.current) {
      const { nextPath, name, type } = lastOpen.current;
      void openFileAt(nextPath, name, type);
      return;
    }
    void listingQuery.refetch();
  }

  const crumbs = path ? path.split('/') : [];

  return (
    <Columns template="20rem minmax(0,1fr)" from="lg" gap="block" className="min-h-[70vh]">
      <Surface as="aside" padding="none" clip>
        <Toolbar className="flex-col items-stretch">
          <div className="flex flex-wrap items-center gap-1">
            <Button type="button" variant="link" onClick={() => navigate('')}>
              {rootLabel}
            </Button>
            {crumbs.map((crumb, index) => (
              <span key={crumbs.slice(0, index + 1).join('/')} className="flex items-center gap-1">
                <Text variant="caption">/</Text>
                <Button
                  type="button"
                  variant="link"
                  onClick={() => navigate(crumbs.slice(0, index + 1).join('/'))}
                >
                  {listing?.path_labels?.[index] ?? crumb}
                </Button>
              </span>
            ))}
          </div>
          <Input
            className="w-full"
            type="search"
            aria-label="Filter files"
            placeholder="Filter files"
            value={search}
            onChange={(event) => dispatch({ type: 'patch', value: { search: event.target.value } })}
          />
        </Toolbar>
        {loading ? (
          <Inset padding="sm">
            <LoadingSkeleton count={8} />
          </Inset>
        ) : null}
        {error ? (
          <Inset padding="sm">
            <ErrorPanel message={error} onRetry={retry} />
          </Inset>
        ) : null}
        {!loading ? (
          <ScrollArea axis="y" maxHeight="64vh" label={`${rootLabel} files`} className="p-2">
            {path ? (
              <Button
                type="button"
                variant="nav"
                onClick={() => navigate(crumbs.slice(0, -1).join('/'))}
              >
                dir ..
              </Button>
            ) : null}
            {items.map((item) => {
              const itemPath = path ? `${path}/${item.name}` : item.name;
              return (
                <Button
                  key={item.name}
                  type="button"
                  variant="nav"
                  className={(openFile?.path ?? opening) === itemPath ? 'is-selected' : undefined}
                  onClick={() => openItem(item.name, item.is_dir, item.type)}
                >
                  <Text variant="data" tone="muted">
                    {item.is_dir ? 'dir' : item.type}
                  </Text>
                  <span
                    className="min-w-0 flex-1 truncate"
                    title={item.label ? `${item.label} (${item.name})` : item.name}
                  >
                    {item.label ?? item.name}
                  </span>
                  {!item.is_dir && item.size !== null ? (
                    <Text variant="caption">{(item.size / 1024).toFixed(1)} KB</Text>
                  ) : null}
                </Button>
              );
            })}
          </ScrollArea>
        ) : null}
      </Surface>

      <section className="min-w-0">
        {opening ? (
          <LoadingSkeleton variant="line" count={12} label={`Opening ${opening}`} />
        ) : null}
        {!openFile && !opening ? (
          <EmptyState
            title="Open an artifact"
            hint="Choose a parquet, Markdown, JSON, or YAML file"
          />
        ) : null}
        {/* Keyed by file: a new key discards the previous file's placeholder payload and
            the viewer's carried-over local state (mode, column page, search). */}
        {openFile?.kind === 'parquet' ? (
          <DatasetViewer key={`${scope}:${openFile.path}`} path={openFile.path} scope={scope} />
        ) : null}
        {openFile?.kind === 'markdown' ? (
          <Stack gap="heading">
            <div>
              <Text as="h2" size="lg" weight="semibold">
                {openFile.path}
              </Text>
              <Text as="p" variant="caption">
                {openFile.preview.lines} lines · {openFile.preview.bytes.toLocaleString()} bytes
              </Text>
            </div>
            <ScrollArea axis="y" maxHeight="70vh">
              <Surface as="pre" padding="lg" className="whitespace-pre-wrap">
                {openFile.preview.content}
              </Surface>
            </ScrollArea>
          </Stack>
        ) : null}
        {openFile?.kind === 'structured' ? (
          <Stack gap="heading">
            <div>
              <Text as="h2" size="lg" weight="semibold">
                {openFile.path}
              </Text>
              <Text as="p" variant="caption">
                {openFile.preview.file_type} · {openFile.preview.bytes.toLocaleString()} bytes
              </Text>
            </div>
            <CodeBlock value={JSON.stringify(openFile.preview.content, null, 2)} />
          </Stack>
        ) : null}
      </section>
    </Columns>
  );
}
