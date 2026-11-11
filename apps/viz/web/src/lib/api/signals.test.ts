/**
 * Signals API boundary tests — research catalog lifecycle schemas.
 *
 * USAGE:
 *   pnpm exec vitest run src/lib/api/signals.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';
import {
  signalResearchFamilySchema,
  signalResearchSurfaceSchema,
  signalResearchVersionSchema,
  signalSummarySchema,
} from './signals';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('signal research catalog schemas', () => {
  it('parses the registered production engine version', () => {
    const signal = signalSummarySchema.parse({
      signal_id: 'example-signal-default',
      description: 'Example production signal',
      production_version: 'v000',
      run_count: 1,
      best_accuracy: null,
      best_auc: null,
      latest_run: '2026-01-01T12:00:00Z',
      latest_run_id: 'run-20260101-120000',
      first_prediction: '2015-01-01T00:00:00',
      latest_prediction: '2024-02-20T00:00:00',
    });

    expect(signal.production_version).toBe('v000');
  });

  it('parses a lifecycle-backed family and version', () => {
    const family = signalResearchFamilySchema.parse({
      signal_family: 'example-signal',
      description: 'Signal family: example-signal',
      total_runs: 1,
      version_count: 1,
      versions: ['v001'],
      latest_run: '2026-01-02T00:00:10Z',
    });
    const version = signalResearchVersionSchema.parse({
      signal_family: 'example-signal',
      memory_version: 'v001',
      total_runs: 1,
      run_count: 1,
      latest_run: '2026-01-02T00:00:10Z',
      state: 'invalidated',
      display_state: 'invalidated',
      source: 'research',
      selected_run_id: '20260101T000000Z-r01',
      experiment: 'example-score',
      has_surface: false,
      lifecycle_phase: 'recorded',
      lifecycle_status: 'not_tested',
      invalidation_reason: 'Input fingerprint changed',
    });

    expect(family.versions).toEqual(['v001']);
    expect(version.lifecycle_status).toBe('not_tested');
    expect(version.has_surface).toBe(false);
  });

  it('parses a canonical production baseline version', () => {
    const version = signalResearchVersionSchema.parse({
      signal_family: 'example-signal',
      memory_version: 'v000',
      total_runs: 1,
      run_count: 1,
      latest_run: '2026-01-01T12:00:00Z',
      state: 'promoted',
      display_state: 'baseline',
      source: 'canonical',
      selected_run_id: 'run-20260101-120000',
      experiment: null,
      has_surface: false,
      lifecycle_phase: 'registered',
      lifecycle_status: null,
      invalidation_reason: null,
    });

    expect(version.display_state).toBe('baseline');
    expect(version.source).toBe('canonical');
  });

  it('accepts a research version with a published surface', () => {
    const version = signalResearchVersionSchema.parse({
      signal_family: 'example-signal',
      memory_version: 'v001',
      total_runs: 1,
      run_count: 1,
      latest_run: null,
      state: 'candidate',
      display_state: 'candidate',
      source: 'research',
      selected_run_id: null,
      experiment: null,
      has_surface: true,
      surface_state: 'rejected',
      lifecycle_phase: 'implemented',
      lifecycle_status: 'active',
      invalidation_reason: null,
    });
    expect(version.has_surface).toBe(true);
    expect(version.surface_state).toBe('rejected');
  });
});

describe('signal research surface schema', () => {
  const surface = {
    signal_family: 'example-signal',
    memory_version: 'v001',
    experiment: 'screen',
    run_id: '20260101T000000Z-r01',
    published_at: '2026-01-02T00:00:00+00:00',
    title: 't',
    summary: 's',
    headline: null,
    gates: [],
    disclosures: [],
    provenance: [],
  };
  const summaryOnlyArm = {
    arm_id: 'control',
    label: 'control',
    role: 'control',
    description: '',
    targets: [],
    ic: null,
    quantiles: null,
    metrics: { path: 'm.json', values: { h7_auc: 0.55 } },
  };

  it('accepts an arm without IC or quantile tables', () => {
    const parsed = signalResearchSurfaceSchema.parse({
      ...surface,
      state: 'rejected',
      arms: [summaryOnlyArm],
    });
    expect(parsed.arms[0]?.ic).toBeNull();
    expect(parsed.blocker).toBeNull();
  });

  it('accepts a not_tested surface only without arms', () => {
    const notTested = { ...surface, state: 'not_tested', blocker: 'input X missing' };
    expect(signalResearchSurfaceSchema.parse({ ...notTested, arms: [] }).blocker).toBe(
      'input X missing',
    );
    expect(() =>
      signalResearchSurfaceSchema.parse({ ...notTested, arms: [summaryOnlyArm] }),
    ).toThrow();
    expect(() =>
      signalResearchSurfaceSchema.parse({ ...surface, state: 'candidate', arms: [] }),
    ).toThrow();
  });
});
