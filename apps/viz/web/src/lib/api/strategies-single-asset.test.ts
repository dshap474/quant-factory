/** Single-asset API request and schema contracts. USAGE: pnpm vitest run strategies-single-asset.test.ts. */

// --------------------------------------------------------------------------- #
// Imports and mocks
// --------------------------------------------------------------------------- #

import { beforeEach, describe, expect, it, vi } from 'vitest';

// `getParsed` is the module's transport + Zod boundary in one; stub the transport
// and keep the parse so this test still asserts the schema contract.
const client = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('./client', () => ({
  openapiGet: client.get,
  getParsed: async (path: string, schema: { parse: (value: unknown) => unknown }, init?: unknown) =>
    schema.parse(await client.get(path, init)),
}));

import { getVersionSingleAsset, singleAssetViewSchema } from './strategies';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('single asset API', () => {
  beforeEach(() => client.get.mockReset());

  it('binds strategy, version and asset in the request', async () => {
    client.get.mockResolvedValue({
      available: false,
      reason: 'unsupported',
      strategy_type: 'example',
      memory_version: 'v001',
      run_id: null,
      asset: null,
      assets: [],
      data: [],
    });

    await getVersionSingleAsset('example', 'v001', 'BTC');

    expect(client.get).toHaveBeenCalledWith(
      '/api/backtests/strategy-types/{strategy_type}/versions/{memory_version}/single-asset',
      expect.objectContaining({
        params: {
          path: { strategy_type: 'example', memory_version: 'v001' },
          query: { asset: 'BTC', config_id: undefined },
        },
      }),
    );
  });

  it('preserves a null observed-price gap at the Zod boundary', () => {
    const parsed = singleAssetViewSchema.parse({
      available: true,
      reason: null,
      strategy_type: 'example',
      memory_version: 'v001',
      run_id: 'run-1',
      experiment: 'experiment',
      title: 'Example',
      artifact_contract: 'ordinary_ledger_v1',
      asset: 'BTC',
      assets: ['BTC'],
      cost_bps: 5,
      rebalance_every_bars: 1,
      points_total: 1,
      points_returned: 1,
      downsampled: false,
      first_observed_at: null,
      last_observed_at: null,
      ever_held: false,
      peak_abs_weight_percent: 0,
      ending_contribution_pp: 0,
      methodology: 'Saved ledger.',
      data: [
        {
          timestamp: '2026-01-01T00:00:00Z',
          price: null,
          weight_percent: 0,
          cumulative_contribution_pp: 0,
        },
      ],
    });

    expect(parsed.available && parsed.data[0]?.price).toBeNull();
  });
});
