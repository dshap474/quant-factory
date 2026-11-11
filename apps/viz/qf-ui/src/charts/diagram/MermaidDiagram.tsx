/**
 * Mermaid diagram rendered in the browser from its text source, themed from the chart
 * tokens so it follows light/dark and the app palette. Mermaid (large) loads only when a
 * diagram first renders. `fit="width"` scales the diagram down to the container;
 * `fit="natural"` draws it at its own size (wrap it in a scroller). A source that fails to
 * parse shows the error and the source text instead of a diagram.
 *
 * USAGE:
 *   import { MermaidDiagram } from '@quant-factory/qf-ui/charts/diagram';
 *   <MermaidDiagram label="Strategy pipeline" source={'flowchart TB\n  A --> B'} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useEffect, useId, useRef, useState } from 'react';

import { cn } from '../../lib/cn';
import { useChartTheme } from '../hooks/useChartTheme';

import './MermaidDiagram.css';

// --------------------------------------------------------------------------- #
// Theme
// --------------------------------------------------------------------------- #

/** A token's colour as `#rrggbb` (Mermaid's colour maths can't read oklch or var()). */
function resolveColor(element: Element, token: string, fallback: string): string {
  const value = getComputedStyle(element).getPropertyValue(token).trim();
  const context = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
  if (!value || !context) return fallback;
  context.fillStyle = fallback;
  context.fillStyle = value;
  context.fillRect(0, 0, 1, 1);
  const [r = 0, g = 0, b = 0, a = 0] = context.getImageData(0, 0, 1, 1).data;
  if (a === 0) return fallback;
  return `#${[r, g, b].map((channel) => channel.toString(16).padStart(2, '0')).join('')}`;
}

function themeVariables(element: Element) {
  const color = (token: string, fallback: string) => resolveColor(element, token, fallback);
  const surface = color('--qf-chart-surface', '#141310');
  const control = color('--qf-chart-surface-control', '#242320');
  const text = color('--qf-chart-strong-text', '#ede9df');
  const luminance = Number.parseInt(surface.slice(1, 3), 16);
  return {
    darkMode: luminance < 128,
    background: surface,
    primaryColor: control,
    secondaryColor: control,
    tertiaryColor: surface,
    primaryTextColor: text,
    nodeTextColor: text,
    textColor: text,
    primaryBorderColor: color('--qf-chart-border-strong', '#898578'),
    lineColor: color('--qf-chart-muted-text', '#aaa69b'),
    clusterBkg: surface,
    clusterBorder: color('--qf-chart-border', '#57554e'),
    edgeLabelBackground: surface,
    fontFamily: getComputedStyle(element).getPropertyValue('--qf-chart-font-sans').trim(),
    fontSize: '14px',
  };
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export interface MermaidDiagramProps {
  /** Mermaid source, e.g. `flowchart TB\n  A --> B`. */
  source: string;
  /** Accessible name of the diagram. */
  label: string;
  fit?: 'width' | 'natural';
  className?: string;
}

export function MermaidDiagram({ source, label, fit = 'width', className }: MermaidDiagramProps) {
  const ref = useRef<HTMLDivElement>(null);
  const id = `qf-mermaid-${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  const [error, setError] = useState<string | null>(null);
  // Mermaid bakes colours into the SVG, so a theme change re-renders it.
  const theme = useChartTheme();

  // biome-ignore lint/correctness/useExhaustiveDependencies: theme is read through CSS tokens; its identity is the re-render trigger.
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    let cancelled = false;
    void (async () => {
      const { default: mermaid } = await import('mermaid');
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'base',
        // Flat boxes: the default 'neo' look adds a light drop shadow that glows on dark surfaces.
        look: 'classic',
        themeVariables: themeVariables(element),
        flowchart: { htmlLabels: true, curve: 'linear', wrappingWidth: 400 },
      });
      try {
        const { svg } = await mermaid.render(id, source);
        if (cancelled) return;
        element.innerHTML = svg;
        setError(null);
      } catch (cause) {
        document.getElementById(`d${id}`)?.remove();
        if (!cancelled) setError(cause instanceof Error ? cause.message : String(cause));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, source, theme]);

  return (
    <figure className={cn('qf-diagram', className)} data-fit={fit} aria-label={label}>
      <div ref={ref} className="qf-diagram-canvas" hidden={error !== null} />
      {error !== null ? (
        <figcaption className="qf-diagram-error">
          <p>{`Diagram failed to render: ${error}`}</p>
          <pre>
            <code>{source}</code>
          </pre>
        </figcaption>
      ) : null}
    </figure>
  );
}
