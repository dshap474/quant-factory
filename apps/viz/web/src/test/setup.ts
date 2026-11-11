/**
 * Vitest setup for the viz web tests: deterministic Web Storage.
 *
 * Node ≥ 22 defines an experimental `globalThis.localStorage` accessor that
 * yields `undefined` (with an ExperimentalWarning) unless Node is started with
 * `--localstorage-file`; vitest's jsdom environment keeps globals that already
 * exist, so that accessor shadows jsdom's Storage. Every test file gets a fresh
 * in-memory Storage instead, in every environment, without reading the accessor.
 *
 * USAGE: registered through `test.setupFiles` in vitest.config.ts.
 */

// --------------------------------------------------------------------------- #
// Shims
// --------------------------------------------------------------------------- #

function createMemoryStorage(): Storage {
  const items = new Map<string, string>();
  return {
    get length() {
      return items.size;
    },
    key: (index) => [...items.keys()][index] ?? null,
    getItem: (key) => items.get(String(key)) ?? null,
    setItem: (key, value) => {
      items.set(String(key), String(value));
    },
    removeItem: (key) => {
      items.delete(String(key));
    },
    clear: () => {
      items.clear();
    },
  };
}

for (const name of ['localStorage', 'sessionStorage'] as const) {
  if (Object.getOwnPropertyDescriptor(globalThis, name)?.configurable === false) continue;
  Object.defineProperty(globalThis, name, {
    configurable: true,
    enumerable: true,
    writable: true,
    value: createMemoryStorage(),
  });
}
