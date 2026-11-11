/**
 * Dev-only React Profiler wrapper that records route commit timings.
 *
 * USAGE:
 *   Loaded lazily by AppLayout when import.meta.env.DEV and ?profile=1 —
 *   never imported in production builds. Commits accumulate on
 *   window.__VIZ_PROFILE_COMMITS__ and mirror onto the <html> dataset for
 *   headless scraping (scripts/measure-app.mjs).
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Profiler, type ProfilerOnRenderCallback, type ReactNode } from 'react';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface RouteProfilerProps {
  id: string;
  children: ReactNode;
}

// --------------------------------------------------------------------------- #
// Recorder
// --------------------------------------------------------------------------- #

const recordProfileCommit: ProfilerOnRenderCallback = (
  id,
  phase,
  actualDuration,
  baseDuration,
  startTime,
  commitTime,
) => {
  const target = window as typeof window & {
    __VIZ_PROFILE_COMMITS__?: Array<Record<string, number | string>>;
  };
  const commits = target.__VIZ_PROFILE_COMMITS__ ?? [];
  commits.push({ id, phase, actualDuration, baseDuration, startTime, commitTime });
  target.__VIZ_PROFILE_COMMITS__ = commits.slice(-500);
  document.documentElement.dataset.vizProfileCommits = JSON.stringify(
    target.__VIZ_PROFILE_COMMITS__,
  );
};

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function RouteProfiler({ id, children }: RouteProfilerProps) {
  return (
    <Profiler id={id} onRender={recordProfileCommit}>
      {children}
    </Profiler>
  );
}
