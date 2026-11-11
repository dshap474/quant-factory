/**
 * Architecture diagrams from an architecture document (Mermaid code), rendered in the browser.
 * Every `## ` section is one diagram, picked from a dropdown (the `diagram` query parameter);
 * the section's first ```mermaid block is drawn in its own scrolling pane and the rest of the
 * section is its notes. Strategy families keep it at `docs/ARCHITECTURE.md`, agents at `docs/DIAGRAMS.md`.
 *
 * USAGE:
 *   <ArchitectureDiagrams markdown={markdown} path="agents/lib/example/docs/DIAGRAMS.md" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { ChartFrame } from '@quant-factory/qf-ui/charts/chrome';
import { MermaidDiagram } from '@quant-factory/qf-ui/charts/diagram';
import { SanitizedMarkdown } from '@/pages/docs/SanitizedMarkdown';
import {
  Cluster,
  ScrollArea,
  SegmentedControl,
  SelectControl,
  Stack,
  TerminalSection,
  Text,
  useSearchParamState,
} from '@/ui';

// --------------------------------------------------------------------------- #
// Parsing
// --------------------------------------------------------------------------- #

interface DiagramSection {
  value: string;
  label: string;
  source: string;
  notes: string;
}

/** `# Title`, an intro, then `## Section` blocks each holding one ```mermaid fence and notes. */
function parseDiagrams(markdown: string): { title: string; sections: DiagramSection[] } {
  const [head = '', ...blocks] = markdown.split(/^## /m);
  const title = head.match(/^# (.+)$/m)?.[1]?.trim() ?? 'Architecture';
  const sections = blocks.map((block) => {
    const newline = block.indexOf('\n');
    const label = block.slice(0, newline).trim();
    const body = block.slice(newline + 1);
    const fence = body.match(/```mermaid\n([\s\S]*?)```/);
    return {
      value: label
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, ''),
      label,
      source: fence?.[1] ?? '',
      notes: (fence ? body.replace(fence[0], '') : body).trim(),
    };
  });
  return { title, sections };
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ArchitectureDiagrams({ markdown, path }: { markdown: string; path: string }) {
  const [diagramView, setDiagramView] = useSearchParamState('diagram', '', { replace: true });
  const [diagramSize, setDiagramSize] = useSearchParamState('diagramSize', 'fit', {
    replace: true,
  });

  const { title, sections } = parseDiagrams(markdown);
  const active = sections.find((section) => section.value === diagramView) ?? sections[0];
  if (!active) return <Text tone="muted">The architecture document has no sections.</Text>;
  const natural = diagramSize === 'natural';

  return (
    <Stack gap="section">
      <ChartFrame
        headingLevel={2}
        title={active.label}
        subtitle={title}
        actions={
          <Cluster gap="stack">
            <SelectControl
              ariaLabel="Architecture diagram"
              size="sm"
              options={sections}
              value={active.value}
              onValueChange={setDiagramView}
            />
            <SegmentedControl
              ariaLabel="Diagram size"
              size="sm"
              options={[
                { value: 'fit', label: 'Fit' },
                { value: 'natural', label: '100%' },
              ]}
              value={natural ? 'natural' : 'fit'}
              onValueChange={setDiagramSize}
            />
          </Cluster>
        }
      >
        <ScrollArea axis="both" maxHeight="70dvh" label="Architecture diagram" tabIndex={0}>
          <MermaidDiagram
            label={`${active.label} diagram`}
            source={active.source}
            fit={natural ? 'natural' : 'width'}
          />
        </ScrollArea>
      </ChartFrame>
      {active.notes ? (
        <TerminalSection title="Reading this diagram">
          <SanitizedMarkdown
            page={{
              path,
              title: active.label,
              markdown: active.notes,
              modified: null,
              generated: false,
            }}
          />
        </TerminalSection>
      ) : null}
    </Stack>
  );
}
