/**
 * Read one optional JSON policy from each installed Viz extension.
 *
 * USAGE:
 *   const policies = await readExtensionJson('route-closures.json');
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { readdir, readFile } from 'node:fs/promises';

// --------------------------------------------------------------------------- #
// Discovery
// --------------------------------------------------------------------------- #

export async function readExtensionJson(filename) {
  const root = new URL('../../extensions/', import.meta.url);
  const entries = await readdir(root, { withFileTypes: true }).catch((error) => {
    if (error.code === 'ENOENT') return [];
    throw error;
  });
  const policies = [];
  for (const entry of entries
    .filter((item) => item.isDirectory() && !item.name.startsWith('_'))
    .sort((left, right) => left.name.localeCompare(right.name))) {
    const source = await readFile(new URL(`${entry.name}/${filename}`, root), 'utf8').catch(
      (error) => {
        if (error.code === 'ENOENT') return null;
        throw error;
      },
    );
    if (source !== null) policies.push(JSON.parse(source));
  }
  return policies;
}
