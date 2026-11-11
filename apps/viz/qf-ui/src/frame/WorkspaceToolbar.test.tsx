/**
 * Structure tests for the shared workspace master-controls band.
 *
 * USAGE:
 *   pnpm exec vitest run src/frame/WorkspaceToolbar.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { WorkspaceToolbar } from './WorkspaceToolbar';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('WorkspaceToolbar', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('renders the title, note and actions', () => {
    act(() =>
      root.render(
        <WorkspaceToolbar title="Chart controls" note="Applies to charts" aria-label="Transforms">
          <button type="button">Reset</button>
        </WorkspaceToolbar>,
      ),
    );

    const band = container.querySelector<HTMLDivElement>('div.ui-workspace-toolbar');
    expect(band?.getAttribute('role')).toBe('toolbar');
    expect(band?.getAttribute('aria-label')).toBe('Transforms');
    const copy = band?.querySelector('.ui-workspace-toolbar-copy');
    expect(copy?.textContent).toBe('Chart controlsApplies to charts');
    expect(band?.querySelector('.ui-workspace-toolbar-actions button')?.textContent).toBe('Reset');
  });

  it('omits the copy block when neither title nor note is given', () => {
    act(() =>
      root.render(
        <WorkspaceToolbar>
          <button type="button">Reset</button>
        </WorkspaceToolbar>,
      ),
    );

    expect(container.querySelector('.ui-workspace-toolbar-copy')).toBeNull();
    expect(container.querySelector('.ui-workspace-toolbar-actions')).not.toBeNull();
  });
});
