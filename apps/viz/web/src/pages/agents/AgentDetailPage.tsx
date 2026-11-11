/**
 * Read-only overview, architecture, prompt workspace and documentation for one canonical agent.
 *
 * USAGE:
 *   Routed at /agents/:agentId — the id is a agents/lib directory name.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { ArrowLeft, ArrowRight } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useParams, useSearchParams } from 'react-router';

import { agentDocPath, hasAgentDoc, useAgentDoc } from '@/lib/agent-docs';
import { type AgentPrompt, useAgentPrompts, useAgentReadme } from '@/lib/api/agents';
import type { DocPage } from '@/lib/api/docs';
import { ArchitectureDiagrams } from '@/lib/components/ArchitectureDiagrams';
import {
  Badge,
  Button,
  Cluster,
  Identifier,
  Inset,
  isLoadingData,
  LoadingSkeleton,
  ScrollArea,
  SegmentedControl,
  Stack,
  StateMessage,
  StepNav,
  TerminalPage,
  Text,
} from '@/ui';
import { SanitizedMarkdown } from '../docs/SanitizedMarkdown';
import { AgentOverview } from './AgentOverview';
import { InformationCompressionHistory } from './InformationCompressionOverview';
import { OptimizerHistory } from './OptimizerOverview';

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

type AgentView = 'overview' | 'architecture' | 'runs' | 'prompts' | 'documentation';
const VIEWS: readonly AgentView[] = [
  'overview',
  'architecture',
  'runs',
  'prompts',
  'documentation',
];

function promptMarker(prompt: AgentPrompt): string {
  if (prompt.kind === 'resident-common') return 'P';
  return prompt.kind === 'meta' ? 'M' : String(prompt.stage);
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

/** Loads the agent's DIAGRAMS.md only when its tab is open. */
function AgentArchitecture({ agentId }: { agentId: string }) {
  const diagrams = useAgentDoc(agentId);
  if (!hasAgentDoc(agentId))
    return (
      <StateMessage>{`No ${agentDocPath(agentId)}; add one to show this agent's architecture.`}</StateMessage>
    );
  if (diagrams === null) return <LoadingSkeleton count={8} />;
  return <ArchitectureDiagrams markdown={diagrams} path={agentDocPath(agentId)} />;
}

export function AgentDetailPage() {
  const agentId = useParams().agentId ?? '';
  return <AgentDetailContent key={agentId} agentId={agentId} />;
}

function AgentDetailContent({ agentId }: { agentId: string }) {
  const informationCompression = agentId === 'information-compression';
  const [params, setParams] = useSearchParams();
  const requestedView = params.get('view');
  const view = VIEWS.find((candidate) => candidate === requestedView) ?? 'overview';
  // Agent-specific Runs extensions: their searchable, paged archive beyond the shared table.
  const extension =
    agentId === 'strategy-optimizer' ? (
      <OptimizerHistory />
    ) : informationCompression ? (
      <InformationCompressionHistory />
    ) : null;
  const setView = (next: AgentView) => setParams({ view: next });
  const [selectedPromptId, setSelectedPromptId] = useState<string | null>(null);
  const promptsQuery = useAgentPrompts(agentId);
  const readmeQuery = useAgentReadme(agentId);

  const prompts = promptsQuery.data?.prompts ?? [];
  const selectedPrompt =
    prompts.find((prompt) => prompt.id === selectedPromptId) ?? prompts.at(0) ?? null;
  const selectedIndex = selectedPrompt ? prompts.indexOf(selectedPrompt) : -1;
  const previousPrompt = selectedIndex > 0 ? prompts[selectedIndex - 1] : undefined;
  const nextPrompt = selectedIndex >= 0 ? prompts[selectedIndex + 1] : undefined;
  const agentName = promptsQuery.data?.name ?? readmeQuery.data?.name ?? agentId;

  const promptPage = useMemo<DocPage | null>(
    () =>
      selectedPrompt
        ? {
            path: selectedPrompt.path,
            title: selectedPrompt.name,
            markdown: selectedPrompt.markdown,
            modified: null,
            generated: false,
          }
        : null,
    [selectedPrompt],
  );

  const readmePage = useMemo<DocPage | null>(
    () =>
      readmeQuery.data
        ? {
            path: readmeQuery.data.path,
            title: readmeQuery.data.name,
            markdown: readmeQuery.data.markdown,
            modified: null,
            generated: false,
          }
        : null,
    [readmeQuery.data],
  );

  return (
    <TerminalPage
      title={agentName}
      fill
      tabs={
        <SegmentedControl
          variant="tabs"
          ariaLabel="Agent view"
          value={view}
          options={[
            { value: 'overview', label: 'Overview' },
            { value: 'architecture', label: 'Architecture' },
            { value: 'runs', label: 'Runs' },
            { value: 'prompts', label: 'Prompts' },
            { value: 'documentation', label: 'Documentation' },
          ]}
          onValueChange={setView}
        />
      }
    >
      {view === 'overview' || view === 'runs' ? (
        <ScrollArea fill>
          <Inset padding="md">
            <AgentOverview
              agentId={agentId}
              view={view}
              onRuns={() => setView('runs')}
              extension={extension}
            />
          </Inset>
        </ScrollArea>
      ) : view === 'architecture' ? (
        <ScrollArea fill>
          <Inset padding="md">
            <AgentArchitecture agentId={agentId} />
          </Inset>
        </ScrollArea>
      ) : view === 'prompts' ? (
        <div className="flex min-h-0 flex-1 flex-col" aria-live="polite">
          {isLoadingData(promptsQuery) || (promptsQuery.error && !promptsQuery.data) ? (
            <ScrollArea fill>
              <Inset padding="md">
                {promptsQuery.error && !promptsQuery.data ? (
                  <StateMessage state="error">{promptsQuery.error.message}</StateMessage>
                ) : (
                  <LoadingSkeleton count={8} />
                )}
              </Inset>
            </ScrollArea>
          ) : promptPage && selectedPrompt ? (
            // Keyed so a new step opens at its top.
            <ScrollArea key={selectedPrompt.id} fill>
              <Inset padding="lg">
                <div className="w-full max-w-[44rem]">
                  <Stack gap="section">
                    <StepNav
                      label={informationCompression ? 'Workflow prompts' : 'Resident program'}
                      orientation="horizontal"
                      selectedId={selectedPrompt.id}
                      onSelect={setSelectedPromptId}
                      steps={prompts.map((prompt) => ({
                        id: prompt.id,
                        marker: promptMarker(prompt),
                        title: prompt.name,
                      }))}
                    />
                    <Stack gap="heading">
                      <Text as="h2" size="lg" weight="semibold">
                        {selectedPrompt.name}
                      </Text>
                      <Cluster gap="xs">
                        <Identifier value={selectedPrompt.path} truncate="end" copyable />
                        <Badge variant="ghost" size="sm">
                          tracked source
                        </Badge>
                      </Cluster>
                    </Stack>
                    <SanitizedMarkdown page={promptPage} hideLeadingTitle />
                    <Cluster justify="between">
                      {previousPrompt ? (
                        <Button
                          variant="control"
                          onClick={() => setSelectedPromptId(previousPrompt.id)}
                        >
                          <ArrowLeft aria-hidden="true" />
                          {previousPrompt.name}
                        </Button>
                      ) : (
                        <span />
                      )}
                      {nextPrompt ? (
                        <Button
                          variant="control"
                          onClick={() => setSelectedPromptId(nextPrompt.id)}
                        >
                          {nextPrompt.name}
                          <ArrowRight aria-hidden="true" />
                        </Button>
                      ) : null}
                    </Cluster>
                  </Stack>
                </div>
              </Inset>
            </ScrollArea>
          ) : (
            <StateMessage>No allowlisted prompts for this agent.</StateMessage>
          )}
        </div>
      ) : (
        <ScrollArea fill aria-live="polite">
          <Inset padding="md">
            {isLoadingData(readmeQuery) ? (
              <LoadingSkeleton count={8} />
            ) : readmeQuery.error && !readmeQuery.data ? (
              <StateMessage state="error">{readmeQuery.error.message}</StateMessage>
            ) : readmePage ? (
              <SanitizedMarkdown page={readmePage} />
            ) : (
              <StateMessage>No README for this agent.</StateMessage>
            )}
          </Inset>
        </ScrollArea>
      )}
    </TerminalPage>
  );
}
