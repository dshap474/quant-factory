/**
 * Agents workspace: canonical-agent navigator plus routed content. /agents itself
 * is the live dashboard, so the navigator lists only agents. The navigator hides
 * on the full-bleed optimizer run route.
 *
 * USAGE:
 *   Declared as the parent route for /agents.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useState } from 'react';
import { useLocation } from 'react-router';

import { useAgents } from '@/lib/api/agents';
import { isLoadingData, Navigator, type NavigatorGroup, SectionLayout } from '@/ui';

// --------------------------------------------------------------------------- #
// Navigator
// --------------------------------------------------------------------------- #

function AgentsNavigator() {
  const { pathname } = useLocation();
  const agentsQuery = useAgents();
  const [query, setQuery] = useState('');
  const queryNormalized = query.trim().toLowerCase();
  const matches = (...values: string[]) =>
    !queryNormalized || values.some((value) => value.toLowerCase().includes(queryNormalized));
  const isActive = (to: string) => pathname === to || pathname.startsWith(`${to}/`);

  const agents = (agentsQuery.data?.agents ?? []).filter((agent) =>
    matches(agent.name, agent.id, agent.status),
  );
  const groups: NavigatorGroup[] = [];
  if (agents.length > 0) {
    groups.push({
      id: 'agents',
      label: 'Canonical agents',
      meta: agents.length,
      items: agents.map((agent) => {
        const to = `/agents/${encodeURIComponent(agent.id)}`;
        return { id: agent.id, label: agent.name, to, current: isActive(to), title: agent.id };
      }),
    });
  }

  return (
    <Navigator
      title="Agents"
      titleTo="/agents"
      listLabel="Agent catalog"
      search={{
        id: 'agent-search',
        label: 'Search agents',
        placeholder: 'Search agents',
        value: query,
        onChange: setQuery,
      }}
      loading={isLoadingData(agentsQuery)}
      error={agentsQuery.error ? `Failed to load agents: ${agentsQuery.error.message}` : null}
      empty={query ? `No agents match “${query}”.` : 'No canonical agents.'}
      groups={groups}
    />
  );
}

// --------------------------------------------------------------------------- #
// Layout
// --------------------------------------------------------------------------- #

export function AgentsLayout() {
  return (
    <SectionLayout
      navigator={<AgentsNavigator />}
      navigatorHiddenOn="/agents/strategy-optimizer/runs/:runId"
    />
  );
}
