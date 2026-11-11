/**
 * Stale-chunk detection and one-shot recovery reload.
 *
 * A deploy replaces the hashed chunk files a long-lived tab still points at, so
 * the next lazy route import rejects. One reload fixes it; a reload loop does
 * not, hence the session-scoped cooldown.
 *
 * USAGE:
 *   if (isChunkLoadError(error) && reloadForStaleChunk()) return <Loading />;
 */

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

const RELOAD_COOLDOWN_MS = 10_000;
const RELOAD_STAMP_KEY = 'qf:viz:chunk-reload-at';

const CHUNK_ERROR_PATTERNS = [
  'Failed to fetch dynamically imported module',
  'error loading dynamically imported module',
  'Importing a module script failed',
];

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export interface ReloadDeps {
  storage?: StorageLike | null;
  now?: () => number;
  reload?: () => void;
}

// --------------------------------------------------------------------------- #
// Detection
// --------------------------------------------------------------------------- #

/** True when `error` looks like a failed dynamic-import of a stale chunk. */
export function isChunkLoadError(error: unknown): boolean {
  const message =
    error instanceof Error
      ? `${error.name}: ${error.message}`
      : typeof error === 'string'
        ? error
        : '';
  if (!message) return false;
  return CHUNK_ERROR_PATTERNS.some((pattern) =>
    message.toLowerCase().includes(pattern.toLowerCase()),
  );
}

// --------------------------------------------------------------------------- #
// Recovery
// --------------------------------------------------------------------------- #

function defaultStorage(): StorageLike | null {
  try {
    return typeof sessionStorage === 'undefined' ? null : sessionStorage;
  } catch {
    return null;
  }
}

/**
 * Reload the document to pick up fresh chunks, at most once per 10 seconds.
 * Returns whether a reload was triggered.
 */
export function reloadForStaleChunk(deps: ReloadDeps = {}): boolean {
  const storage = deps.storage === undefined ? defaultStorage() : deps.storage;
  const now = deps.now ?? (() => Date.now());
  const reload = deps.reload ?? (() => window.location.reload());

  const at = now();
  const previous = Number.parseInt(storage?.getItem(RELOAD_STAMP_KEY) ?? '', 10);
  if (Number.isFinite(previous) && at - previous < RELOAD_COOLDOWN_MS) {
    return false;
  }

  try {
    storage?.setItem(RELOAD_STAMP_KEY, String(at));
  } catch {
    // A storage failure must not block the recovery reload.
  }
  reload();
  return true;
}
