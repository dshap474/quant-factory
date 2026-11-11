/**
 * Validate a published API response using the actual research-page Zod schema.
 * No browser, application server, or lake writes are started by this checker.
 *
 * USAGE:
 *   node scripts/check-research-surface.mjs <API-response.json-or-URL>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

// --------------------------------------------------------------------------- #
// Entry point
// --------------------------------------------------------------------------- #

const [source, ...extra] = process.argv.slice(2);
if (!source || extra.length) {
  throw new Error('Usage: check-research-surface.mjs <API-response.json-or-URL>');
}

const server = await createServer({
  root: fileURLToPath(new URL('..', import.meta.url)),
  configFile: false,
  logLevel: 'error',
  server: { middlewareMode: true, watch: null, hmr: false, ws: false },
  appType: 'custom',
  optimizeDeps: { noDiscovery: true, include: [] },
});

try {
  let payload;
  if (/^https?:\/\//.test(source)) {
    const response = await fetch(source, { signal: AbortSignal.timeout(30_000) });
    if (!response.ok) throw new Error(`Surface request failed: HTTP ${response.status}`);
    payload = await response.json();
  } else {
    payload = JSON.parse(await readFile(source, 'utf8'));
  }
  const { researchSurfaceSchema } = await server.ssrLoadModule('/src/lib/api/strategies.ts');
  const surface = researchSurfaceSchema.parse(payload);
  console.log(
    JSON.stringify({
      status: 'passed',
      strategy_type: surface.strategy_type,
      memory_version: surface.memory_version,
      run_id: surface.run_id,
      rows: surface.data.length,
    }),
  );
} finally {
  await server.close();
}
