/**
 * A child route that throws is caught by the route error element and rendered
 * inside the parent layout, not in place of it.
 *
 * USAGE:
 *   pnpm exec vitest run src/layouts/RouteErrorBoundary.test.tsx
 *
 * @vitest-environment jsdom
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { createMemoryRouter, Outlet, RouterProvider } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { RouteErrorBoundary } from './RouteErrorBoundary';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// --------------------------------------------------------------------------- #
// Fixtures
// --------------------------------------------------------------------------- #

function ParentLayout() {
  return (
    <div data-testid="parent-layout">
      <Outlet />
    </div>
  );
}

function Boom(): never {
  throw new Error('boom in render');
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  vi.spyOn(console, 'error').mockImplementation(() => {});
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

// --------------------------------------------------------------------------- #
// Tests
// --------------------------------------------------------------------------- #

describe('RouteErrorBoundary', () => {
  it('renders the failure inside the parent layout', () => {
    const router = createMemoryRouter(
      [
        {
          path: '/',
          element: <ParentLayout />,
          errorElement: <RouteErrorBoundary />,
          children: [{ path: 'boom', element: <Boom />, errorElement: <RouteErrorBoundary /> }],
        },
      ],
      { initialEntries: ['/boom'] },
    );

    act(() => {
      root.render(<RouterProvider router={router} />);
    });

    const layout = container.querySelector('[data-testid="parent-layout"]');
    expect(layout).not.toBeNull();

    const alert = container.querySelector('[role="alert"]');
    expect(alert).not.toBeNull();
    expect(alert?.textContent).toContain('boom in render');
    expect(layout?.contains(alert)).toBe(true);
    expect(container.textContent).toContain('Something went wrong');
  });
});
