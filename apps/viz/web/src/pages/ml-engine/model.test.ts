/**
 * ML Engine workspace selection and status-label tests.
 *
 * USAGE:
 *   pnpm test -- src/pages/ml-engine/model.test.ts
 */

// --------------------------------------------------------------------------- #
// Imports and fixtures
// --------------------------------------------------------------------------- #

import { describe, expect, it } from 'vitest';

import type { MlEngineRun } from '@/lib/api/mlEngine';

import {
  artifactLabel,
  completionSummary,
  elapsedDuration,
  matchesFilters,
  progressLabel,
  selectRunId,
  visibleStages,
} from './model';

const baseRun: MlEngineRun = {
  schema_version: 1,
  run_id: 'completed-run',
  producer: 'example.trainer',
  status: 'completed',
  operation: 'complete',
  stage: 'evaluation',
  task: 'regression',
  target: 'target',
  feature_count: 3,
  final_refit: false,
  candidate: 'ridge',
  candidate_index: 1,
  candidate_count: 1,
  fold_index: 3,
  fold_count: 3,
  completed_fits: 3,
  total_fits: 3,
  started_at: '2026-08-24T12:00:00Z',
  updated_at: '2026-08-24T12:01:00Z',
  completed_at: '2026-08-24T12:01:00Z',
  host: 'worker-01',
  inference_ready: false,
  error: null,
};

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('ML Engine workspace model', () => {
  it('selects only an explicitly requested valid run', () => {
    expect(selectRunId('completed-run')).toBe('completed-run');
    expect(selectRunId('missing-run')).toBe('missing-run');
    expect(selectRunId('bad$id')).toBeNull();
    expect(selectRunId(null)).toBeNull();
  });

  it('matches a run against status and producer-family filters', () => {
    const familyRun = { ...baseRun, producer: 'example-strategy/v004' };
    expect(matchesFilters(baseRun, 'all', 'all')).toBe(true);
    expect(matchesFilters(baseRun, 'running', 'all')).toBe(false);
    expect(matchesFilters(familyRun, 'all', 'example-strategy')).toBe(true);
    expect(matchesFilters(familyRun, 'all', 'example-strategy2')).toBe(false);
    expect(matchesFilters(familyRun, 'failed', 'example-strategy')).toBe(false);
  });

  it('distinguishes running, failed, inference-ready, and OOS-only labels', () => {
    expect(artifactLabel({ ...baseRun, status: 'running' }, false)).toBe(
      'OOS-only run; no inference artifact',
    );
    expect(artifactLabel({ ...baseRun, status: 'running', final_refit: true }, false)).toBe(
      'Artifact pending',
    );
    expect(artifactLabel({ ...baseRun, status: 'failed' }, false)).toContain('failed');
    expect(artifactLabel({ ...baseRun, inference_ready: true }, true)).toBe(
      'Inference-ready artifact',
    );
    expect(artifactLabel(baseRun, false)).toBe('OOS-only run; no inference artifact');
    expect(progressLabel(baseRun)).toBe('3 / 3');
  });

  it('shows only stages that a terminal run could have reached', () => {
    expect(visibleStages(baseRun)).toEqual([
      'validation',
      'planning',
      'cross_validation',
      'evaluation',
    ]);
    expect(
      visibleStages({
        ...baseRun,
        stage: 'artifact_save',
        final_refit: true,
        inference_ready: true,
      }),
    ).toEqual([
      'validation',
      'planning',
      'cross_validation',
      'evaluation',
      'selection',
      'final_refit',
      'artifact_save',
    ]);
  });

  it('shows sub-second elapsed time without rounding it to zero', () => {
    expect(
      elapsedDuration({
        ...baseRun,
        started_at: '2026-08-24T12:00:00.000Z',
        completed_at: '2026-08-24T12:00:00.500Z',
      }),
    ).toBe('<1s');
  });

  it('extracts readable selection and metric facts from artifact metadata', () => {
    const summary = completionSummary({
      path: 'db/ml-engine/completed-run',
      manifest: null,
      config: null,
      schema: null,
      selection: {
        selected_name: 'lightgbm',
        selected_candidates: ['lightgbm'],
        primary_metric: 'rmse',
        direction: 'minimize',
        candidates: { lightgbm: { eligible: true } },
      },
      metrics: {
        lightgbm: {
          coverage: 1,
          metrics: { rmse: 1.4380518725502556 },
          n_folds: 4,
          n_observations: 32,
          n_periods: 32,
        },
      },
    });

    expect(summary.selection).toEqual([
      ['Selected models', 'lightgbm'],
      ['Primary metric', 'rmse'],
      ['Direction', 'minimize'],
    ]);
    expect(summary.metrics).toEqual([
      ['rmse', '1.43805'],
      ['Coverage', '100%'],
      ['Folds', '4'],
      ['OOS observations', '32'],
      ['OOS periods', '32'],
    ]);
  });
});
