/**
 * Agent documents bundled from the repository: each agent's architecture diagrams
 * (`agents/lib/<agent>/docs/DIAGRAMS.md`). Files load on demand; editing one reloads it (hot
 * reload in dev, next build otherwise).
 *
 * USAGE:
 *   hasAgentDoc('wiki-ingestor')                // boolean
 *   const markdown = useAgentDoc(agentId);       // string | null
 *   agentDocPath(agentId)                        // repo-relative path, for doc links
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useBundledText } from './strategy-docs';

// --------------------------------------------------------------------------- #
// Files
// --------------------------------------------------------------------------- #

const ROOT = '../../../../../';

const FILES = import.meta.glob<string>('../../../../../agents/lib/*/docs/DIAGRAMS.md', {
  query: '?raw',
  import: 'default',
});

export function agentDocPath(agentId: string): string {
  return `agents/lib/${agentId}/docs/DIAGRAMS.md`;
}

export function hasAgentDoc(agentId: string): boolean {
  return `${ROOT}${agentDocPath(agentId)}` in FILES;
}

/** The agent's DIAGRAMS.md, or null while loading or when it has none. */
export function useAgentDoc(agentId: string): string | null {
  return useBundledText(FILES[`${ROOT}${agentDocPath(agentId)}`]);
}
