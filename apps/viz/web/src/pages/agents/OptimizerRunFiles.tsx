/** Scoped experiment file list and bounded reader.
 * USAGE: <OptimizerRunFiles runId={id} scope="version" path="SPEC.md" onSelect={select} />
 */

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@quant-factory/qf-ui/tables';
// --------------------------------------------------------------------------- #
// Imports and file presentation
// --------------------------------------------------------------------------- #
import { Check, Copy, Download, FileText, Folder, FolderUp } from 'lucide-react';
import { useState } from 'react';
import {
  type OptimizerFileScope,
  optimizerFileUrl,
  useOptimizerFile,
  useOptimizerFiles,
} from '@/lib/api/optimizer';
import {
  Button,
  Cluster,
  CodeBlock,
  Input,
  Inset,
  isLoadingData,
  Link,
  LoadingSkeleton,
  ScrollArea,
  Stack,
  StateMessage,
  Surface,
  Text,
  useToast,
} from '@/ui';
import { normalizeDocPath, resolveRelativeDocPath } from '../docs/markdown';
import { SanitizedMarkdown } from '../docs/SanitizedMarkdown';

export const fileScopes: { value: OptimizerFileScope; label: string }[] = [
  { value: 'version', label: 'Version files' },
  { value: 'attempt', label: 'Attempt files' },
  { value: 'research', label: 'Research artifacts' },
];
function sizeLabel(bytes: number | null) {
  if (bytes === null) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// --------------------------------------------------------------------------- #
// File browser
// --------------------------------------------------------------------------- #
export function OptimizerRunFiles({
  runId,
  scope,
  path,
  directory,
  roots,
  live,
  onSelect,
}: {
  runId: string;
  scope: OptimizerFileScope;
  path: string | null;
  directory: string;
  roots: Record<string, string>;
  live: boolean;
  onSelect: (scope: OptimizerFileScope, path: string | null, directory?: string) => void;
}) {
  const { toast } = useToast();
  const [search, setSearch] = useState('');
  const [copied, setCopied] = useState<string | null>(null);
  const [rawFile, setRawFile] = useState<string | null>(null);
  const selection = `${scope}:${path}`;
  const raw = rawFile === selection;
  const listing = useOptimizerFiles(runId, scope, directory, live);
  const preview = useOptimizerFile(runId, scope, path, live);
  const file = preview.data;
  const entries = (listing.data?.entries ?? []).filter((entry) =>
    entry.name.toLowerCase().includes(search.toLowerCase()),
  );
  const parent = directory.split('/').slice(0, -1).join('/');
  const selectionFor = (absolute: string): { scope: OptimizerFileScope; path: string } | null => {
    const normalized = normalizeDocPath(absolute);
    for (const item of fileScopes) {
      const root = normalizeDocPath(roots[item.value] ?? '');
      if (root && (normalized === root || normalized?.startsWith(`${root}/`)))
        return { scope: item.value, path: normalized.slice(root.length + 1) };
    }
    return null;
  };
  const resolveHref = (href: string, currentPath: string) => {
    const absolute = href.startsWith('/')
      ? normalizeDocPath(href.split('#')[0])
      : resolveRelativeDocPath(href, currentPath);
    const target = absolute ? selectionFor(absolute) : null;
    if (!target) return null;
    const isDirectory =
      href.split('#')[0].endsWith('/') || !target.path.split('/').pop()?.includes('.');
    const params = new URLSearchParams({
      scope: target.scope,
      file: isDirectory ? '' : target.path,
    });
    if (isDirectory && target.path) params.set('directory', target.path);
    return `?${params}${href.includes('#') ? `#${href.split('#')[1]}` : ''}`;
  };
  return (
    <div className="grid min-h-72 min-w-0 flex-1 grid-cols-1 grid-rows-[minmax(10rem,14rem)_minmax(18rem,1fr)] max-sm:min-h-[32rem] sm:grid-cols-[minmax(15rem,20rem)_minmax(0,1fr)] sm:grid-rows-1">
      <Surface
        as="aside"
        padding="none"
        clip
        aria-label="Experiment files"
        className="flex min-h-0 min-w-0 flex-col"
      >
        <Inset padding="sm">
          <Stack gap="heading">
            <Input
              type="search"
              placeholder="Find a file…"
              aria-label="Find a file"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <Cluster gap="stack">
              <Button
                icon
                variant="control"
                disabled={!directory}
                aria-label="Parent folder"
                onClick={() => {
                  setSearch('');
                  onSelect(scope, null, parent);
                }}
              >
                <FolderUp size={16} />
              </Button>
              <span title={listing.data?.location} className="truncate">
                {directory || fileScopes.find((item) => item.value === scope)?.label}
              </span>
            </Cluster>
          </Stack>
        </Inset>
        <ScrollArea fill>
          {isLoadingData(listing) ? (
            <LoadingSkeleton variant="table" count={8} />
          ) : listing.error && !listing.data ? (
            <StateMessage state="error" compact>
              Files unavailable.
            </StateMessage>
          ) : (
            <Table density="dense">
              <TableHeader sticky>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead numeric className="whitespace-nowrap">
                    Size
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {entries.map((entry) => (
                  <TableRow key={entry.path} aria-selected={entry.path === path}>
                    <TableCell>
                      <Button
                        variant="nav"
                        onClick={() => {
                          setRawFile(null);
                          setSearch('');
                          onSelect(
                            scope,
                            entry.directory ? null : entry.path,
                            entry.directory ? entry.path : directory,
                          );
                        }}
                        title={entry.name}
                      >
                        {entry.directory ? <Folder size={16} /> : <FileText size={16} />}
                        <span className="truncate">{entry.name}</span>
                      </Button>
                    </TableCell>
                    <TableCell numeric className="whitespace-nowrap">
                      {sizeLabel(entry.bytes)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {!isLoadingData(listing) && listing.data && entries.length === 0 && (
            <StateMessage compact>
              {search ? 'No matching files.' : 'No files in this folder yet.'}
            </StateMessage>
          )}
          {listing.data?.truncated && (
            <StateMessage compact>This folder lists its first 1,000 entries only.</StateMessage>
          )}
        </ScrollArea>
      </Surface>
      <Surface
        as="section"
        padding="none"
        aria-label="File preview"
        className="flex min-h-0 min-w-0 flex-1 flex-col"
      >
        <Surface variant="panel" padding="sm">
          <Cluster justify="between">
            <Stack gap="none" className="min-w-0">
              <Text as="strong" size="sm" className="truncate">
                {path?.split('/').pop() ?? 'File preview'}
              </Text>
              <span title={file?.location} className="block truncate">
                <Text as="span" variant="data" tone="muted">
                  {path ?? 'Choose a file to inspect'}
                </Text>
              </span>
            </Stack>
            {path && (
              <Cluster gap="stack">
                {file?.markdown && (
                  <Button
                    variant="control"
                    aria-pressed={raw}
                    onClick={() => setRawFile(raw ? null : selection)}
                  >
                    {raw ? 'Preview' : 'Source'}
                  </Button>
                )}
                {file && (
                  <Button
                    variant="control"
                    icon
                    aria-label="Copy file path"
                    title="Copy file path"
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(file.location);
                        setCopied(file.location);
                        toast({ title: 'Copied', description: file.location, tone: 'success' });
                      } catch {
                        setCopied(null);
                        toast({
                          title: 'Copy failed',
                          description: file.location,
                          tone: 'critical',
                        });
                      }
                    }}
                  >
                    {copied === file.location ? <Check size={16} /> : <Copy size={16} />}
                  </Button>
                )}
                <Link
                  href={`${optimizerFileUrl(runId, scope, path)}&download=true`}
                  download
                  variant="control"
                  icon
                  aria-label="Download file"
                  title="Download file"
                >
                  <Download size={16} />
                </Link>
              </Cluster>
            )}
          </Cluster>
        </Surface>
        <ScrollArea fill>
          <Inset padding="sm">
            {/* biome-ignore lint/a11y/useKeyWithClickEvents: Native links provide keyboard activation; this delegates their clicks. */}
            <div
              key={selection}
              onClick={(event) => {
                const anchor = event.target instanceof Element ? event.target.closest('a') : null;
                const href = anchor?.getAttribute('href');
                if (
                  !href ||
                  !file ||
                  href.startsWith('#') ||
                  event.metaKey ||
                  event.ctrlKey ||
                  event.shiftKey
                )
                  return;
                if (href.startsWith('?')) {
                  const params = new URLSearchParams(href.split('#')[0]);
                  const nextScope = params.get('scope');
                  if (fileScopes.some((item) => item.value === nextScope) && params.has('file')) {
                    event.preventDefault();
                    onSelect(
                      nextScope as OptimizerFileScope,
                      params.get('file') || null,
                      params.get('directory') ?? undefined,
                    );
                  }
                }
              }}
            >
              {!path ? (
                <StateMessage>Select a file from the list.</StateMessage>
              ) : isLoadingData(preview) ? (
                <LoadingSkeleton count={10} />
              ) : preview.error && !file ? (
                <StateMessage state="error">
                  File unavailable. It may have moved or not been written yet.
                </StateMessage>
              ) : file?.text === null ? (
                <StateMessage>
                  Binary file · {sizeLabel(file.bytes)}. Download to inspect.
                </StateMessage>
              ) : file ? (
                <>
                  {file.truncated && (
                    <Text as="p" variant="caption">
                      Preview shows the first 256 KB. Download for the complete file.
                    </Text>
                  )}
                  {file.markdown && !raw ? (
                    <SanitizedMarkdown
                      page={{
                        path: file.location,
                        title: file.name,
                        markdown: file.text ?? '',
                        generated: false,
                        modified: null,
                      }}
                      links={{ toHref: (value) => value, resolveHref }}
                    />
                  ) : (
                    <CodeBlock value={file.text ?? ''} />
                  )}
                </>
              ) : null}
            </div>
          </Inset>
        </ScrollArea>
      </Surface>
    </div>
  );
}
