/**
 * Enforce one gzip limit on the JavaScript `dist/index.html` fetches before the app paints:
 * the entry module script and each `modulepreload` chunk. It exists to catch a mistake such
 * as a chart library landing in first load, not to track ordinary growth.
 *
 * USAGE:
 *   pnpm run build
 *   pnpm run check:bundle
 *   node scripts/check-bundle.mjs --report   # JSON of every measured value
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { readFile } from 'node:fs/promises';
import { gzipSync } from 'node:zlib';

// --------------------------------------------------------------------------- #
// Budget
// --------------------------------------------------------------------------- #

const KIB = 1024;

// Leaves modest headroom over the current first load. Only raise this for a dependency that
// has to be in first load; otherwise move the new code behind a route or a lazy import.
const FIRST_LOAD_JS_LIMIT_KIB = 175;

// --------------------------------------------------------------------------- #
// Measurement
// --------------------------------------------------------------------------- #

const distDirectory = new URL('../dist/', import.meta.url);

/** The first-load assets `index.html` declares: entry script, modulepreloads, stylesheets. */
function collectFirstLoadHrefs(html) {
  const hrefs = [];
  for (const [, attrs] of html.matchAll(/<script\b([^>]*)>/g)) {
    if (!/type=["']module["']/.test(attrs)) continue;
    const src = attrs.match(/\bsrc=["']([^"']+)["']/);
    if (src?.[1]) hrefs.push({ href: src[1], kind: 'js' });
  }
  for (const [, attrs] of html.matchAll(/<link\b([^>]*)>/g)) {
    const rel = attrs.match(/\brel=["']([^"']+)["']/)?.[1];
    const href = attrs.match(/\bhref=["']([^"']+)["']/)?.[1];
    if (!href) continue;
    if (rel === 'modulepreload') hrefs.push({ href, kind: 'js' });
    else if (rel === 'stylesheet') hrefs.push({ href, kind: 'css' });
  }
  return hrefs;
}

async function measureFirstLoad() {
  const html = await readFile(new URL('index.html', distDirectory), 'utf8');
  const assets = [];
  for (const { href, kind } of collectFirstLoadHrefs(html)) {
    const file = href.replace(/^\/+/, '');
    const bytes = gzipSync(await readFile(new URL(file, distDirectory))).byteLength;
    assets.push({ href, kind, kib: Number((bytes / KIB).toFixed(2)) });
  }
  return assets;
}

// --------------------------------------------------------------------------- #
// Check
// --------------------------------------------------------------------------- #

async function checkBundle({ report }) {
  const assets = await measureFirstLoad();
  const sumKib = (kind) =>
    assets.filter((asset) => asset.kind === kind).reduce((sum, asset) => sum + asset.kib, 0);
  const totalJsKib = Number(sumKib('js').toFixed(2));

  if (report) {
    console.log(
      JSON.stringify({ firstLoadAssets: assets, firstLoadTotalJsKib: totalJsKib }, null, 2),
    );
    return;
  }
  if (assets.length === 0) {
    throw new Error('Build assets are missing. Run `pnpm run build` before this check.');
  }
  if (totalJsKib > FIRST_LOAD_JS_LIMIT_KIB) {
    console.error(
      `Bundle budget failed: first-load JS is ${totalJsKib.toFixed(2)} KiB (limit ${FIRST_LOAD_JS_LIMIT_KIB} KiB)`,
    );
    process.exitCode = 1;
    return;
  }
  console.log(
    `Bundle budget passed: first-load JS ${totalJsKib.toFixed(2)} of ${FIRST_LOAD_JS_LIMIT_KIB} KiB, CSS ${sumKib('css').toFixed(2)} KiB.`,
  );
}

// --------------------------------------------------------------------------- #
// Entry point
// --------------------------------------------------------------------------- #

await checkBundle({ report: process.argv.includes('--report') });
