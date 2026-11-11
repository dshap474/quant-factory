/**
 * Preserved NOT TESTED strategy-version record.
 *
 * USAGE:
 *   <InvalidatedStrategyVersion title="Example Strategy / v002" strategyType="…" memoryVersion="v002" version={summary} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';
import { invalidationLink } from '@/extensions';
import type { StrategyVersionSummary } from '@/lib/api/strategies';
import {
  Badge,
  Cluster,
  Link,
  Stack,
  StatGrid,
  StatItem,
  TerminalPage,
  TerminalSection,
  Text,
} from '@/ui';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface InvalidatedStrategyVersionProps {
  kicker?: string;
  title: string;
  strategyType: string;
  memoryVersion: string;
  version: StrategyVersionSummary;
  navigation?: ReactNode;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function InvalidatedStrategyVersion({
  kicker,
  title,
  strategyType,
  memoryVersion,
  version,
  navigation,
}: InvalidatedStrategyVersionProps) {
  const scoredObservations = version.scored_observations ?? 0;
  const isLifecycleRecord = version.lifecycle_status === 'not_tested';
  const successor = invalidationLink(strategyType, memoryVersion);
  return (
    <TerminalPage kicker={kicker} title={title} tabs={navigation}>
      <TerminalSection title="preserved research record">
        <Stack gap="block" className="max-w-3xl">
          <Cluster gap="stack">
            {!isLifecycleRecord ? (
              <Badge tone="critical" size="md">
                INVALIDATED
              </Badge>
            ) : null}
            <Badge tone="warning" size="md">
              NOT TESTED
            </Badge>
          </Cluster>
          <Stack gap="stack">
            <Text as="h2" size="lg" weight="bold">
              {isLifecycleRecord
                ? 'Backtest not run.'
                : 'The prospective protocol stopped before scoring.'}
            </Text>
            <div className="text-pretty">
              <Text as="p" tone="muted" size="sm">
                {version.invalidation_reason ??
                  (isLifecycleRecord
                    ? 'The recorded prerequisites did not pass. See Details for the findings.'
                    : 'The frozen research inputs no longer matched the authenticated historical evidence.')}
              </Text>
            </div>
          </Stack>
          <StatGrid variant="strip" boxed columns={2}>
            <StatItem
              label={isLifecycleRecord ? 'Research phase' : 'Prospective observations scored'}
              value={isLifecycleRecord ? version.lifecycle_phase : scoredObservations}
            />
            <StatItem
              label="Recorded run"
              value={
                version.selected_run_id ??
                (isLifecycleRecord ? 'No account run' : 'No anchor created')
              }
              title={version.selected_run_id ?? undefined}
            />
          </StatGrid>
          {isLifecycleRecord ? (
            <Link to={`/strategies/${strategyType}/${memoryVersion}?view=details`} variant="inline">
              View findings and review records
            </Link>
          ) : null}
        </Stack>
      </TerminalSection>

      {successor ? (
        <TerminalSection title="supersession">
          <Text as="p" tone="muted" size="sm">
            The artifacts remain preserved for audit history. The refreshed experiment continues as{' '}
            <Link to={successor.to} variant="inline">
              {successor.label}
            </Link>
            .
          </Text>
        </TerminalSection>
      ) : null}
    </TerminalPage>
  );
}
