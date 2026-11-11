/**
 * Generate OpenAPI TypeScript types for the viz React SPA.
 *
 * USAGE:
 *   pnpm run generate:api
 *   pnpm run check:api
 *
 * The checked-in snapshot always comes from the zero-extension application
 * factory, never from a mutable development server.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// --------------------------------------------------------------------------- #
// Paths
// --------------------------------------------------------------------------- #

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const repoRoot = path.resolve(root, '../../..');
const generatedDir = path.join(root, 'src/lib/api/generated');
const openapiPath = path.join(generatedDir, 'openapi.json');
const schemaPath = path.join(generatedDir, 'schema.d.ts');
const mode = process.argv.includes('--check') ? 'check' : 'generate';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function sha256(text) {
  return createHash('sha256').update(text).digest('hex');
}

function generatePublicOpenApi() {
  const source = [
    'import json',
    'from db_api.main import create_app',
    'print(json.dumps(create_app(load_extensions=False).openapi(), indent=2))',
  ].join('; ');
  return execFileSync('uv', ['run', 'python', '-c', source], {
    cwd: repoRoot,
    encoding: 'utf8',
    env: {
      ...process.env,
      PYTHONPATH: path.join(repoRoot, 'apps/api/src'),
    },
  });
}

function runOpenapiTypescript(inputPath, outputPath) {
  execFileSync('pnpm', ['exec', 'openapi-typescript', inputPath, '-o', outputPath], {
    cwd: root,
    stdio: 'inherit',
  });
}

// --------------------------------------------------------------------------- #
// Main
// --------------------------------------------------------------------------- #

mkdirSync(generatedDir, { recursive: true });

if (mode === 'check') {
  if (!existsSync(openapiPath) || !existsSync(schemaPath)) {
    console.error('check:api failed: missing generated OpenAPI artifacts');
    process.exit(1);
  }
  // Regenerate to a temp path so a failed check never dirties schema.d.ts.
  const tmpDir = mkdtempSync(path.join(tmpdir(), 'viz-check-api-'));
  const tmpSchema = path.join(tmpDir, 'schema.d.ts');
  try {
    const generatedOpenApi = `${JSON.stringify(JSON.parse(generatePublicOpenApi()), null, 2)}\n`;
    if (sha256(readFileSync(openapiPath, 'utf8')) !== sha256(generatedOpenApi)) {
      console.error('check:api failed: openapi.json is not the current public-core schema');
      process.exit(1);
    }
    const before = readFileSync(schemaPath, 'utf8');
    runOpenapiTypescript(openapiPath, tmpSchema);
    const after = readFileSync(tmpSchema, 'utf8');
    if (sha256(before) !== sha256(after)) {
      console.error('check:api failed: schema.d.ts is out of date. Run pnpm run generate:api');
      process.exit(1);
    }
    console.log('check:api ok — schema.d.ts matches openapi.json');
    process.exit(0);
  } finally {
    rmSync(tmpDir, { recursive: true, force: true });
  }
}

// Pretty-print for stable diffs
const openapiJson = `${JSON.stringify(JSON.parse(generatePublicOpenApi()), null, 2)}\n`;
writeFileSync(openapiPath, openapiJson);
runOpenapiTypescript(openapiPath, schemaPath);
console.log(
  'generate:api ok — wrote openapi.json + schema.d.ts from create_app(load_extensions=False)',
);
