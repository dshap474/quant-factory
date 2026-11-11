/**
 * Binds qf-ui's router adapter to React Router so kit links, the shell navigator,
 * and `useSearchParamState` navigate client-side.
 *
 * USAGE:
 *   // Anywhere inside a React Router context (AppShell mounts it for the app):
 *   <ViewerRouterProvider>{children}</ViewerRouterProvider>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { type QfRouterAdapter, QfRouterProvider } from '@quant-factory/qf-ui';
import type { ReactNode } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router';

// --------------------------------------------------------------------------- #
// Adapter
// --------------------------------------------------------------------------- #

function useRouterPathname(): string {
  return useLocation().pathname;
}

export const VIEWER_ROUTER_ADAPTER: QfRouterAdapter = {
  Link,
  usePathname: useRouterPathname,
  useNavigate,
  useSearchParams,
};

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export interface ViewerRouterProviderProps {
  children: ReactNode;
}

export function ViewerRouterProvider({ children }: ViewerRouterProviderProps) {
  return <QfRouterProvider adapter={VIEWER_ROUTER_ADAPTER}>{children}</QfRouterProvider>;
}
