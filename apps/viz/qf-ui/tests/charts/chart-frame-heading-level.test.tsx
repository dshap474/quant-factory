/**
 * ChartFrame renders its title at the requested heading level.
 *
 * USAGE:
 *   pnpm test -- chart-frame-heading-level.test.tsx
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { ChartFrame } from '../../src/charts/components/ChartFrame';
import { TimeSeriesChart } from '../../src/charts/components/TimeSeriesChart';

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('ChartFrame heading level', () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
  });

  afterEach(() => host.remove());

  async function mount(node: ReactNode): Promise<void> {
    const root = createRoot(host);
    await act(async () => root.render(node));
  }

  function titleTag(): string | undefined {
    return host.querySelector('.qf-chart-frame-title')?.tagName;
  }

  it('defaults the title to h3', async () => {
    await mount(<ChartFrame title="Price history">body</ChartFrame>);
    expect(titleTag()).toBe('H3');
  });

  it('renders at the requested level', async () => {
    await mount(
      <ChartFrame title="Price history" headingLevel={2}>
        body
      </ChartFrame>,
    );
    expect(titleTag()).toBe('H2');
  });

  it('threads the level through TimeSeriesChart', async () => {
    await mount(
      <TimeSeriesChart title="Composite score" headingLevel={2}>
        <div />
      </TimeSeriesChart>,
    );
    expect(titleTag()).toBe('H2');
    expect(host.textContent).toContain('Composite score');
  });
});
