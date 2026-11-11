/**
 * Pure run-display rules shared by the Live Dashboard, agent pages and the run page:
 * execution state, titles, stage segments and cost text.
 *
 * USAGE:
 *   import { runState, runTitle, stageSegments } from './runs';
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { AgentRun, AgentRunStage, AgentStep } from '@/lib/api/agent-runs';
import { formatDuration, liveStatusTone, pluralize, type StageBarSegment } from '@/ui';

// --------------------------------------------------------------------------- #
// State
// --------------------------------------------------------------------------- #

export function isActive(run: AgentRun): boolean {
  return run.status === 'starting' || run.status === 'running';
}

/** Recorded as active and not observed dead: a gone supervisor's run belongs in history. */
export function isRunning(run: AgentRun): boolean {
  return isActive(run) && run.health !== 'interrupted';
}

/** Health only overrides a status where it contradicts a claimed live supervisor. */
export function runState(run: AgentRun): string {
  if (!isActive(run)) return run.status;
  if (run.health === 'unresponsive' || run.health === 'interrupted') return run.health;
  if (run.health === 'unknown') return 'unknown';
  return run.status;
}

const STATE_LABELS: Record<string, string> = {
  succeeded: 'Succeeded',
  starting: 'Starting',
  running: 'Running',
  checking: 'Checking',
  failed: 'Failed',
  cancelled: 'Cancelled',
  interrupted: 'Interrupted',
  unknown: 'Unknown',
  unresponsive: 'Unresponsive',
};

export function stateLabel(state: string): string {
  return STATE_LABELS[state] ?? state;
}

// --------------------------------------------------------------------------- #
// Labels
// --------------------------------------------------------------------------- #

export function agentName(agentId: string): string {
  return agentId
    .split('-')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/** The human label, else the target, else the legacy source's leaf, else the id. */
export function runTitle(run: AgentRun): string {
  return run.label ?? run.target ?? run.legacy_source?.split('/').pop() ?? run.id;
}

export function runHref(runId: string): string {
  return `/agents/runs/${encodeURIComponent(runId)}`;
}

export function binding(step: AgentStep | null): string {
  if (!step?.model) return '—';
  return step.reasoning ? `${step.model} · ${step.reasoning}` : step.model;
}

/** Models this run used, from its stages; the run's live step as a fallback. */
export function runModels(run: AgentRun): string[] {
  const models = new Set(run.stages.flatMap((stage) => stage.models));
  const current = run.active_steps.find((step) => step.model)?.model ?? run.last_step?.model;
  if (models.size === 0 && current) models.add(current);
  return [...models];
}

// --------------------------------------------------------------------------- #
// Numbers
// --------------------------------------------------------------------------- #

/** Dollars at a precision that keeps sub-cent spend readable; `≥` when some steps lack cost. */
export function formatCost(value: number | null | undefined, complete = true): string {
  if (value === null || value === undefined) return '—';
  const digits = value > 0 && value < 0.1 ? 4 : 2;
  return `${complete ? '' : '≥'}$${value.toFixed(digits)}`;
}

export function stageDetail(stage: AgentRunStage): string {
  const failed = (stage.counts.failed ?? 0) + (stage.counts.interrupted ?? 0);
  return [
    stateLabel(stage.status),
    `${stage.count} ${pluralize(stage.count, 'step')}`,
    failed ? `${failed} failed` : null,
    formatDuration(stage.elapsed_seconds),
    stage.cost_usd === null ? null : formatCost(stage.cost_usd),
  ]
    .filter((part) => part && part !== '—')
    .join(' · ');
}

/** One stage-bar segment per recorded stage, widened by elapsed time. */
export function stageSegments(run: AgentRun): StageBarSegment[] {
  return run.stages.map((stage) => ({
    id: stage.name,
    label: stage.name,
    tone: liveStatusTone(stage.status),
    weight: stage.elapsed_seconds,
    detail: stageDetail(stage),
  }));
}
