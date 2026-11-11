/**
 * Exercise the publication checker with complete and incomplete API responses.
 *
 * USAGE: pnpm exec vitest run src/lib/api/research-surface-checker.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { it } from 'vitest';
import { researchSurfaceSchema } from './strategies';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

it('accepts the UI fixture and rejects research-only metric names with a nonzero exit', () => {
  const directory = mkdtempSync(path.join(tmpdir(), 'surface-contract-'));
  try {
    const input = path.join(directory, 'response.json');
    const fixture = researchSurfaceSchema.parse(
      JSON.parse(
        readFileSync(new URL('./__fixtures__/research-surface.json', import.meta.url), 'utf8'),
      ),
    );
    const command = fileURLToPath(
      new URL('../../../scripts/check-research-surface.mjs', import.meta.url),
    );
    writeFileSync(input, JSON.stringify(fixture));
    const valid = spawnSync(process.execPath, [command, input], {
      encoding: 'utf8',
      timeout: 30_000,
    });
    assert.equal(valid.status, 0, valid.stderr);
    assert.equal(JSON.parse(valid.stdout).run_id, fixture.run_id);

    const malformed = {
      ...fixture,
      metrics: Object.fromEntries(
        Object.entries(fixture.metrics ?? {}).map(([role, metrics]) => [
          role,
          {
            total_return: metrics.total_return,
            sharpe: metrics.sharpe,
            max_drawdown: metrics.max_drawdown,
            final_equity: 200_000,
            cagr: metrics.annualized_return,
            volatility_365: metrics.annualized_volatility,
          },
        ]),
      ),
    };
    writeFileSync(input, JSON.stringify(malformed));
    const invalid = spawnSync(process.execPath, [command, input], {
      encoding: 'utf8',
      timeout: 30_000,
    });
    assert.equal(invalid.status, 1, invalid.stderr);
    assert.match(invalid.stderr, /ZodError/);
    assert.match(invalid.stderr, /ending_value/);
    assert.match(invalid.stderr, /annualized_volatility/);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}, 30_000);
