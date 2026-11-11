/**
 * Shared OpenAPI client + JSON helpers for the React viz SPA.
 *
 * USAGE:
 *   import { getParsed, requestParsed } from './client';
 *   const rows = await getParsed('/api/signals', z.array(signalSummarySchema));
 *   const doc = await requestParsed(`/api/docs/page/${p}`, docPageSchema);
 *
 * Caching: TanStack Query owns server-state cache/staleTime, so this module
 * implements no TTL or in-flight request map of its own.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import createClient, { type ClientPathsWithMethod, type MaybeOptionalInit } from 'openapi-fetch';
import type { output, ZodType } from 'zod';
import { ApiError, detailFromUnknown } from './errors';
import type { paths } from './generated/schema';

// --------------------------------------------------------------------------- #
// OpenAPI client
// --------------------------------------------------------------------------- #

/** Typed openapi-fetch client. Paths include the `/api` prefix (and `/health`). */
export const apiClient = createClient<paths>({ baseUrl: '' });

// --------------------------------------------------------------------------- #
// Low-level JSON request
// --------------------------------------------------------------------------- #

export interface RequestJsonOptions {
  method?: string;
  body?: unknown;
  headers?: HeadersInit;
  signal?: AbortSignal;
  cache?: RequestCache;
  /** Optional fetch override (tests). */
  fetch?: typeof globalThis.fetch;
}

/**
 * Fetch JSON from an absolute app path (`/api/...` or `/health`).
 * Prefer this for catch-all lake paths; use `apiClient` for simple OpenAPI routes.
 */
export async function requestJson<T>(path: string, options: RequestJsonOptions = {}): Promise<T> {
  const fetchFn = options.fetch ?? globalThis.fetch;
  const method = (options.method ?? 'GET').toUpperCase();
  const headers = new Headers(options.headers);
  if (options.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetchFn(path, {
    method,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
    cache: options.cache,
  });

  if (!response.ok) {
    const errorBody: unknown = await response.json().catch(() => ({
      detail: `HTTP ${response.status}`,
    }));
    throw new ApiError(detailFromUnknown(errorBody, `HTTP ${response.status}`), response.status);
  }

  const data = (await response.json()) as T;
  if (data == null) {
    throw new ApiError('Empty response body', response.status || 500);
  }
  return data;
}

/** Every path in the generated schema that declares a GET operation. */
export type ApiGetPath = ClientPathsWithMethod<typeof apiClient, 'get'>;

/** The path/query params openapi-fetch accepts for one GET route. */
export type ApiGetInit<Path extends ApiGetPath> = MaybeOptionalInit<paths[Path], 'get'>;

/**
 * openapi-fetch GET helper that throws ApiError on failure and returns data.
 * The route literal and its params are checked against the generated schema.
 * Response bodies are untyped there (almost no response models), so the result
 * is `unknown` and its type comes from a Zod schema — see `getParsed`.
 */
export async function openapiGet<Path extends ApiGetPath>(
  path: Path,
  init?: ApiGetInit<Path>,
): Promise<unknown> {
  const { data, error, response } = await apiClient.GET(
    path,
    // openapi-fetch spreads init as a tuple whose optionality it computes per
    // route; for a still-generic `Path` that tuple is unresolved, so widen the
    // one argument. `path` and the init's shape stay schema-checked.
    init as ApiGetInit<Path> & { [key: string]: unknown },
  );
  const status = response?.status ?? 500;
  if (error || !response?.ok) {
    throw new ApiError(detailFromUnknown(error, `HTTP ${status}`), status);
  }
  if (data == null) {
    throw new ApiError('Empty response body', status);
  }
  return data;
}

// --------------------------------------------------------------------------- #
// Parsed request helpers
// --------------------------------------------------------------------------- #

/**
 * GET a schema-checked route and validate the body. The result type is the
 * schema's output, so call sites never restate it.
 */
export async function getParsed<Path extends ApiGetPath, Schema extends ZodType>(
  path: Path,
  schema: Schema,
  init?: ApiGetInit<Path>,
): Promise<output<Schema>> {
  return schema.parse(await openapiGet(path, init));
}

/**
 * `requestJson` plus validation, for catch-all lake paths that carry an encoded
 * suffix and so are not route literals in the generated schema.
 */
export async function requestParsed<Schema extends ZodType>(
  path: string,
  schema: Schema,
  options: RequestJsonOptions = {},
): Promise<output<Schema>> {
  return schema.parse(await requestJson<unknown>(path, options));
}
