/**
 * Plain History API router adapter for the standalone example: no router library.
 * Links push a history entry and every subscriber re-reads `location.pathname`.
 *
 * USAGE:
 *   <QfRouterProvider adapter={historyAdapter}>{app}</QfRouterProvider>
 *   const pathname = usePathname();
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { QfNavigateOptions, QfRouteLinkProps, QfRouterAdapter } from '@quant-factory/qf-ui';
import { type MouseEvent, useSyncExternalStore } from 'react';

// --------------------------------------------------------------------------- #
// History store
// --------------------------------------------------------------------------- #

function subscribe(onChange: () => void): () => void {
  window.addEventListener('popstate', onChange);
  return () => window.removeEventListener('popstate', onChange);
}

export function navigate(to: string, options?: QfNavigateOptions): void {
  if (options?.replace) window.history.replaceState(options.state ?? null, '', to);
  else window.history.pushState(options?.state ?? null, '', to);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

export function usePathname(): string {
  return useSyncExternalStore(
    subscribe,
    () => window.location.pathname,
    () => '/',
  );
}

// --------------------------------------------------------------------------- #
// Adapter
// --------------------------------------------------------------------------- #

function HistoryLink({ to, state, onClick, ...rest }: QfRouteLinkProps) {
  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(to, { state });
  };
  return <a href={to} onClick={handleClick} {...rest} />;
}

export const historyAdapter: QfRouterAdapter = {
  Link: HistoryLink,
  usePathname,
  useNavigate: () => navigate,
};
