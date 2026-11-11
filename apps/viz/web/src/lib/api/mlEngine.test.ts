/**
 * ML Engine API boundary and polling tests.
 *
 * USAGE:
 *   pnpm test -- src/lib/api/mlEngine.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports and fixtures
// --------------------------------------------------------------------------- #

import { beforeEach, describe, expect, it, vi } from 'vitest';

import { openapiGet as untypedOpenapiGet } from './client';
import {
  listMlEngineProducers,
  listMlEngineRuns,
  ML_ENGINE_ACTIVE_POLL_MS,
  ML_ENGINE_IDLE_POLL_MS,
  mlEngineKeys,
  mlEngineRunDetailSchema,
  mlEngineRunListSchema,
  mlEngineRunSchema,
  runDetailPollInterval,
  runListPollInterval,
} from './mlEngine';

// `getParsed` is the module's transport + Zod boundary in one; stub the transport
// and keep the parse so these tests still assert the schema contract.
const transport = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('./client', () => ({
  openapiGet: transport.get,
  getParsed: async (path: string, schema: { parse: (value: unknown) => unknown }, init?: unknown) =>
    schema.parse(await transport.get(path, init)),
}));

interface OpenapiGetCall {
  params?: { query?: Record<string, string | undefined> };
}

const openapiGet = vi.mocked(untypedOpenapiGet) as unknown as ReturnType<
  typeof vi.fn<(path: string, init?: OpenapiGetCall) => Promise<unknown>>
>;

const runningRun = {
  schema_version: 1 as const,
  run_id: '20240102T120000Z-demo',
  producer: 'example.trainer',
  status: 'running' as const,
  operation: 'fit candidate ridge on fold 2',
  stage: 'cross_validation' as const,
  task: 'regression',
  target: 'return_1d',
  feature_count: 32,
  final_refit: true,
  candidate: 'ridge',
  candidate_index: 1,
  candidate_count: 2,
  fold_index: 2,
  fold_count: 4,
  completed_fits: 1,
  total_fits: 8,
  started_at: '2024-01-02T12:00:00Z',
  updated_at: '2024-01-02T12:00:05Z',
  completed_at: null,
  host: 'worker-01',
  inference_ready: false,
  error: null,
};

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('ML Engine API schemas', () => {
  it('accepts running, inference-ready, OOS-only, and failed states', () => {
    const ready = {
      ...runningRun,
      run_id: 'ready-run',
      status: 'completed' as const,
      stage: 'artifact_save' as const,
      completed_at: '2024-01-02T12:01:00Z',
      inference_ready: true,
    };
    const oosOnly = {
      ...ready,
      run_id: 'oos-run',
      stage: 'evaluation' as const,
      final_refit: false,
      inference_ready: false,
    };
    const failed = {
      ...runningRun,
      run_id: 'failed-run',
      status: 'failed' as const,
      completed_at: '2024-01-02T12:00:10Z',
      error: { type: 'ValueError', message: 'invalid training matrix' },
    };

    expect(mlEngineRunSchema.parse(runningRun).status).toBe('running');
    expect(mlEngineRunSchema.parse(ready).inference_ready).toBe(true);
    expect(mlEngineRunSchema.parse(oosOnly).final_refit).toBe(false);
    expect(mlEngineRunSchema.parse(failed).error?.type).toBe('ValueError');
  });

  it('accepts safe artifact metadata', () => {
    const detail = mlEngineRunDetailSchema.parse({
      run: { ...runningRun, status: 'completed', completed_at: runningRun.updated_at },
      artifact: {
        path: 'db/ml-engine/20240102T120000Z-demo',
        manifest: { format: 'ml-engine' },
        config: {},
        schema: { features: ['a', 'b'] },
        metrics: { validation_score: 0.42 },
        selection: { selected: ['ridge'] },
      },
    });
    expect(detail.artifact?.metrics?.validation_score).toBe(0.42);
  });

  it('rejects malformed and unsupported payloads', () => {
    expect(() => mlEngineRunSchema.parse({ ...runningRun, schema_version: 2 })).toThrow();
    expect(() => mlEngineRunSchema.parse({ ...runningRun, completed_fits: -1 })).toThrow();
    expect(() => mlEngineRunSchema.parse({ ...runningRun, unexpected: true })).toThrow();
    expect(() =>
      mlEngineRunListSchema.parse({ runs: [runningRun], count: 1, invalid_count: 'one' }),
    ).toThrow();
  });
});

describe('ML Engine request construction', () => {
  beforeEach(() => {
    openapiGet.mockReset();
  });

  it('sends run filters to the API instead of narrowing the fetched page', async () => {
    openapiGet.mockResolvedValue({ runs: [], count: 0, invalid_count: 0 });

    await listMlEngineRuns();
    await listMlEngineRuns({ producer: 'example-strategy', status: 'running' });

    expect(openapiGet.mock.calls[0]?.[0]).toBe('/api/ml-engine/runs');
    expect(openapiGet.mock.calls[0]?.[1]?.params?.query).toEqual({
      producer: undefined,
      status: undefined,
    });
    expect(openapiGet.mock.calls[1]?.[1]?.params?.query).toEqual({
      producer: 'example-strategy',
      status: 'running',
    });
  });

  it('separates cached pages by filter and reads producers from their own route', async () => {
    expect(mlEngineKeys.list()).not.toEqual(mlEngineKeys.list({ status: 'failed' }));
    expect(mlEngineKeys.list({ producer: 'a' })).not.toEqual(mlEngineKeys.list({ producer: 'b' }));

    openapiGet.mockResolvedValue({ producers: ['batch.example'], invalid_count: 0 });
    const producers = await listMlEngineProducers();

    expect(openapiGet.mock.calls[0]?.[0]).toBe('/api/ml-engine/producers');
    expect(producers.producers).toEqual(['batch.example']);
  });
});

describe('ML Engine polling', () => {
  const activeRun = { ...runningRun, updated_at: new Date().toISOString() };

  it('polls the list quickly only while a returned run is active', () => {
    expect(runListPollInterval({ runs: [activeRun], count: 1, invalid_count: 0 })).toBe(
      ML_ENGINE_ACTIVE_POLL_MS,
    );
    expect(runListPollInterval({ runs: [], count: 0, invalid_count: 0 })).toBe(
      ML_ENGINE_IDLE_POLL_MS,
    );
  });

  it('treats a running run with a stale heartbeat as a zombie and polls idle', () => {
    expect(runListPollInterval({ runs: [runningRun], count: 1, invalid_count: 0 })).toBe(
      ML_ENGINE_IDLE_POLL_MS,
    );
    expect(runDetailPollInterval({ run: runningRun, artifact: null })).toBe(ML_ENGINE_IDLE_POLL_MS);
  });

  it('polls selected detail quickly only while it is active', () => {
    expect(runDetailPollInterval({ run: activeRun, artifact: null })).toBe(
      ML_ENGINE_ACTIVE_POLL_MS,
    );
    expect(
      runDetailPollInterval({
        run: { ...activeRun, status: 'completed', completed_at: activeRun.updated_at },
        artifact: null,
      }),
    ).toBe(ML_ENGINE_IDLE_POLL_MS);
  });
});
