/**
 * Pure presentation helpers for the ML Engine run workspace.
 *
 * USAGE:
 *   const selected = selectRunId(requestedRunId);
 *   const belongs = matchesFilters(run, 'running', 'all');
 *
 * Run filtering itself belongs to the API; the run list is a bounded page.
 */

// --------------------------------------------------------------------------- #
// Imports and types
// --------------------------------------------------------------------------- #

import { ML_ENGINE_STAGES, type MlEngineRun, type MlEngineRunDetail } from '@/lib/api/mlEngine';

export type RunFilter = 'all' | 'running' | 'completed' | 'failed';
export type CompletionFact = [label: string, value: string];

export interface CompletionSummary {
  selection: CompletionFact[];
  metrics: CompletionFact[];
}

const RUN_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

// --------------------------------------------------------------------------- #
// Selection and filtering
// --------------------------------------------------------------------------- #

export function selectRunId(requested: string | null): string | null {
  return requested && RUN_ID_PATTERN.test(requested) ? requested : null;
}

export function producerFamily(producer: string): string {
  const slash = producer.indexOf('/');
  return slash === -1 ? producer : producer.slice(0, slash);
}

/** True when a run belongs in the page the current filters asked the API for. */
export function matchesFilters(run: MlEngineRun, filter: RunFilter, producer: string): boolean {
  return (
    (filter === 'all' || run.status === filter) &&
    (producer === 'all' || producerFamily(run.producer) === producer)
  );
}

// --------------------------------------------------------------------------- #
// Labels and formatting
// --------------------------------------------------------------------------- #

export function artifactLabel(run: MlEngineRun, artifactPresent: boolean): string {
  if (run.status === 'failed') return 'No artifact — training failed';
  if (run.inference_ready && artifactPresent) return 'Inference-ready artifact';
  if (run.final_refit === false) return 'OOS-only run; no inference artifact';
  if (run.status === 'running') return 'Artifact pending';
  return 'No inference artifact';
}

export function visibleStages(run: MlEngineRun): MlEngineRun['stage'][] {
  const currentIndex = ML_ENGINE_STAGES.indexOf(run.stage);
  return ML_ENGINE_STAGES.filter((stage, index) => {
    if (run.status !== 'running' && index > currentIndex) return false;
    if (stage === 'ensemble') return run.stage === 'ensemble';
    if (stage === 'final_refit') return run.final_refit === true;
    if (stage === 'artifact_save') return run.stage === 'artifact_save' || run.inference_ready;
    return true;
  });
}

export function progressLabel(run: MlEngineRun): string {
  if (run.total_fits === null) return `${run.completed_fits} / —`;
  return `${run.completed_fits} / ${run.total_fits}`;
}

export function relativeAge(timestamp: string, now = Date.now()): string {
  const elapsedSeconds = Math.max(0, Math.floor((now - Date.parse(timestamp)) / 1_000));
  if (!Number.isFinite(elapsedSeconds) || elapsedSeconds < 5) return 'just now';
  if (elapsedSeconds < 60) return `${elapsedSeconds}s ago`;
  const minutes = Math.floor(elapsedSeconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export function elapsedDuration(run: MlEngineRun, now = Date.now()): string {
  const end = run.completed_at ? Date.parse(run.completed_at) : now;
  const elapsedMilliseconds = Math.max(0, end - Date.parse(run.started_at));
  if (!Number.isFinite(elapsedMilliseconds)) return '—';
  if (elapsedMilliseconds < 1_000) return '<1s';
  const seconds = Math.floor(elapsedMilliseconds / 1_000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

export function shortRunId(runId: string): string {
  if (runId.length <= 22) return runId;
  return `…${runId.slice(-21)}`;
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];
}

function label(value: string): string {
  return value.replaceAll('_', ' ');
}

function number(value: unknown): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  return value.toLocaleString(undefined, { maximumSignificantDigits: 6 });
}

export function completionSummary(artifact: MlEngineRunDetail['artifact']): CompletionSummary {
  if (!artifact) return { selection: [], metrics: [] };
  const selection = record(artifact.selection);
  const selected = strings(selection?.selected_candidates);
  const selectedName =
    selected[0] ?? (typeof selection?.selected_name === 'string' ? selection.selected_name : null);
  const selectionFacts: CompletionFact[] = [];
  if (selected.length > 0) selectionFacts.push(['Selected models', selected.join(', ')]);
  else if (selectedName) selectionFacts.push(['Selected model', selectedName]);
  if (typeof selection?.primary_metric === 'string') {
    selectionFacts.push(['Primary metric', label(selection.primary_metric)]);
  }
  if (typeof selection?.direction === 'string') {
    selectionFacts.push(['Direction', selection.direction]);
  }

  const metricsRoot = record(artifact.metrics);
  const candidateMetrics = selectedName ? record(metricsRoot?.[selectedName]) : null;
  const metricValues = record(candidateMetrics?.metrics) ?? metricsRoot;
  const metricFacts: CompletionFact[] = [];
  for (const [name, value] of Object.entries(metricValues ?? {})) {
    const formatted = number(value);
    if (formatted) metricFacts.push([label(name), formatted]);
  }
  const coverage = candidateMetrics?.coverage;
  if (typeof coverage === 'number' && Number.isFinite(coverage)) {
    metricFacts.push([
      'Coverage',
      `${(coverage * 100).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`,
    ]);
  }
  for (const [key, factLabel] of [
    ['n_folds', 'Folds'],
    ['n_observations', 'OOS observations'],
    ['n_periods', 'OOS periods'],
  ] as const) {
    const formatted = number(candidateMetrics?.[key]);
    if (formatted) metricFacts.push([factLabel, formatted]);
  }
  return { selection: selectionFacts, metrics: metricFacts.slice(0, 7) };
}
