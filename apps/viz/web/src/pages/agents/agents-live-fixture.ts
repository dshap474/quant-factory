/** Isolated test fixtures; never persisted to the producer store.
 * USAGE: imported by Agents dashboard unit and browser tests only.
 */

// --------------------------------------------------------------------------- #
// Fixture
// --------------------------------------------------------------------------- #

import type {
  AgentRun,
  AgentRunActivity,
  AgentRunDetail,
  AgentRunStats,
  AgentRuns,
  AgentStep,
} from '@/lib/api/agent-runs';

export function stepFixture(runId: string, name: string, workItem: string | null): AgentStep {
  return {
    id: `${runId}-${name}-${workItem ?? 'run'}`,
    run_id: runId,
    name,
    work_item: workItem,
    status: 'running',
    started_at: '2026-01-01T00:00:00+00:00',
    finished_at: null,
    engine: 'test-engine',
    model: 'test-model',
    reasoning: 'high',
    activity: 'calling test-model',
    activity_source: 'runner',
    updated_at: '2026-01-01T00:00:00+00:00',
    completed_units: null,
    total_units: null,
    exit_code: null,
    error: null,
    elapsed_seconds: 5,
    input_tokens: null,
    output_tokens: null,
    cache_read_tokens: null,
    cache_write_tokens: null,
    thinking_tokens: null,
    cost_usd: null,
    cost_basis: null,
    wall_seconds: null,
  };
}

export function runFixture(id = 'fixture-001'): AgentRun {
  const step = stepFixture(id, 'author', 'candidate-1');
  return {
    id,
    agent_id: 'strategy-optimizer',
    target: 'fixture-family v001',
    host_id: null,
    status: 'running',
    started_at: '2026-01-01T00:00:00+00:00',
    finished_at: null,
    heartbeat_at: '2026-01-01T00:00:05+00:00',
    resumed_from_run_id: null,
    error: null,
    legacy_source: null,
    elapsed_seconds: 5,
    health: 'responsive',
    health_detail: null,
    active_steps: [step],
    active_step_count: 1,
    step_counts: { running: 1 },
    step_total: 1,
    last_step: step,
    last_activity_at: '2026-01-01T00:00:00+00:00',
    unresolved: false,
    label: null,
    subject_run_id: null,
    subject: null,
    reviews: [],
    attempt: { number: 1, count: 1 },
    totals: null,
    stages: [
      {
        name: 'author',
        status: 'running',
        counts: { running: 1 },
        count: 1,
        started_at: '2026-01-01T00:00:00+00:00',
        finished_at: null,
        elapsed_seconds: 5,
        cost_usd: null,
        models: ['test-model'],
      },
    ],
  };
}

export function snapshotFixture(runs: AgentRun[] = [runFixture()]): AgentRuns {
  const active = (run: AgentRun) => run.status === 'running' || run.status === 'starting';
  return {
    fetched_at: '2026-01-01T00:00:05+00:00',
    store: { available: true, schema_version: 1, detail: null },
    runs,
    coverage: [
      {
        agent_id: 'strategy-optimizer',
        name: 'Strategy Optimizer',
        status: 'monitored',
        steps: ['author', 'audit', 'seal'],
        records: runs.filter((run) => run.agent_id === 'strategy-optimizer').length,
        detail: 'Records every attempt of its official entry point',
      },
      {
        agent_id: 'information-compression',
        name: 'Information Compression',
        status: 'not-monitored',
        steps: [],
        records: 0,
        detail: 'No run reporting declared; runs are not observable here',
      },
    ],
    active_count: runs.filter(active).length,
    attention_count: runs.filter((run) => ['failed', 'unknown', 'interrupted'].includes(run.status))
      .length,
    unresolved_count: runs.filter((run) => run.unresolved).length,
    history_total: runs.filter((run) => !active(run)).length,
    history_limit: 30,
    steps_truncated: false,
    process_snapshot_available: true,
    host_id: 'fixture-host',
  };
}

export function detailFixture(run: AgentRun, steps = run.active_steps): AgentRunDetail {
  return {
    run,
    steps,
    step_total: steps.length,
    limit: 12,
    offset: 0,
    fetched_at: '2026-01-01T00:00:05+00:00',
  };
}

export function activityFixture(run: AgentRun, texts = ['calling test-model']): AgentRunActivity {
  return {
    run_id: run.id,
    entries: texts.map((text, index) => ({
      at: `2026-01-01T00:00:0${index}+00:00`,
      step_id: run.last_step?.id ?? null,
      source: 'runner',
      text,
    })),
    available: true,
    truncated: false,
    malformed: 0,
  };
}

export function statsFixture(runs: AgentRun[] = [runFixture()]): AgentRunStats {
  return {
    fetched_at: '2026-01-01T00:00:05+00:00',
    days: 14,
    window: {
      runs_24h: runs.length,
      failed_24h: runs.filter((run) => run.status === 'failed').length,
      cost_24h: null,
      cost_7d: null,
      cost_complete_7d: true,
      last_finished_at: null,
    },
    agents: [],
  };
}
