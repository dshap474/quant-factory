/**
 * Canonical autonomous-agent inventory.
 *
 * USAGE:
 *   Routed at /agents.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { AgentSummary } from '@/lib/api/agents';
import { useAgents } from '@/lib/api/agents';
import type { PipelineRow } from '@/ui';
import {
  isLoadingData,
  PipelineArchitectureMap,
  pluralize,
  SegmentedControl,
  TerminalPage,
  useSearchParamChoice,
} from '@/ui';
import { AgentsLiveDashboard } from './agents/AgentsLiveDashboard';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

const VIEWS = ['live', 'catalog'] as const;

function readiness(label: string, ready: boolean): string {
  return `${label} ${ready ? 'ready' : 'missing'}`;
}

function agentRow(agent: AgentSummary): PipelineRow {
  const steps = agent.prompt_steps.length;
  const parts = [
    readiness('program', agent.program_ready),
    readiness('driver', agent.driver_ready),
    readiness('tests', agent.tests_ready),
    `${steps} ${pluralize(steps, 'step')}`,
    agent.path,
  ];
  // The API status often restates a readiness fact ("program missing"); show it once.
  if (!parts.includes(agent.status)) parts.unshift(agent.status);
  return {
    key: agent.id,
    detail: parts.join(' · '),
    id: `agent-${encodeURIComponent(agent.id)}`,
    href: `/agents/${encodeURIComponent(agent.id)}`,
  };
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function AgentsPage() {
  const [view, setView] = useSearchParamChoice('view', VIEWS, 'live');
  const query = useAgents();
  const rows = (query.data?.agents ?? []).map(agentRow);

  return (
    <TerminalPage
      title="Agents"
      tabs={
        <SegmentedControl
          variant="tabs"
          ariaLabel="Agents view"
          value={view}
          options={[
            { value: 'live', label: 'Live Dashboard' },
            { value: 'catalog', label: 'Catalog' },
          ]}
          onValueChange={setView}
        />
      }
    >
      {view === 'live' ? (
        <AgentsLiveDashboard />
      ) : (
        <PipelineArchitectureMap
          scope="agents"
          hideHeader
          laneRows={{
            '01': {
              rows,
              loading: isLoadingData(query),
              empty: query.error ? 'agent inventory unavailable' : 'no canonical agents',
            },
          }}
        />
      )}
    </TerminalPage>
  );
}
