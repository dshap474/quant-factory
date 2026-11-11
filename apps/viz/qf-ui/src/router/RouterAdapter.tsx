/**
 * Router adapter: the one seam between qf-ui navigation components and the host router.
 *
 * qf-ui never imports a router. Components that link to in-app routes (`Link`,
 * `RouteTabs`, `IndexBar`, `DataTable` link cells, the
 * shell `Navigator` and `SidebarShell`) read the host's link component, current
 * pathname, imperative navigate and URL search params from this context. Without a
 * provider they fall back to plain anchors, `window.location` and the History API.
 * `useNavigate` and `useSearchParams` are optional: a host that omits them gets the
 * same fallbacks.
 *
 * USAGE:
 *   // Host app, inside its router:
 *   const adapter: QfRouterAdapter = {
 *     Link: RouterLink,
 *     usePathname: () => useLocation().pathname,
 *     useNavigate,
 *     useSearchParams,
 *   };
 *   <QfRouterProvider adapter={adapter}>{app}</QfRouterProvider>
 *
 *   // Inside qf-ui:
 *   const { Link: RouteLink, useNavigate } = useQfRouter();
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  type ComponentPropsWithoutRef,
  type ComponentType,
  createContext,
  type ReactNode,
  useContext,
  useMemo,
  useSyncExternalStore,
} from 'react';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

/** Props every host link component must accept: anchor props plus a route and location state. */
export interface QfRouteLinkProps extends Omit<ComponentPropsWithoutRef<'a'>, 'href'> {
  to: string;
  state?: unknown;
}

export interface QfNavigateOptions {
  /** Replace the current history entry instead of pushing a new one. */
  replace?: boolean;
  state?: unknown;
}

/** Imperative navigation to an in-app route. */
export type QfNavigate = (to: string, options?: QfNavigateOptions) => void;

/** Next search params, or an updater from the current ones. */
export type QfSearchParamsUpdate =
  | URLSearchParams
  | ((current: URLSearchParams) => URLSearchParams);

export type QfSetSearchParams = (next: QfSearchParamsUpdate, options?: QfNavigateOptions) => void;

export interface QfRouterAdapter {
  /** Client-side link component (for example React Router's `Link`). */
  Link: ComponentType<QfRouteLinkProps>;
  /** Hook returning the current pathname; called unconditionally during render. */
  usePathname: () => string;
  /** Hook returning an imperative navigate function (for example React Router's `useNavigate`). */
  useNavigate?: () => QfNavigate;
  /** Hook returning the URL search params and their setter (for example React Router's `useSearchParams`). */
  useSearchParams?: () => [URLSearchParams, QfSetSearchParams];
}

/** The adapter as qf-ui reads it: every hook present, host or fallback. */
export type QfResolvedRouterAdapter = Required<QfRouterAdapter>;

export interface QfRouterProviderProps {
  adapter: QfRouterAdapter;
  children: ReactNode;
}

// --------------------------------------------------------------------------- #
// Fallback adapter
// --------------------------------------------------------------------------- #

function AnchorRouteLink({ to, state: _state, ...rest }: QfRouteLinkProps) {
  return <a href={to} {...rest} />;
}

function useWindowPathname(): string {
  return typeof window === 'undefined' ? '/' : window.location.pathname;
}

function navigateWindow(to: string, options?: QfNavigateOptions): void {
  if (typeof window === 'undefined') return;
  if (options?.replace) window.location.replace(to);
  else window.location.assign(to);
}

function useWindowNavigate(): QfNavigate {
  return navigateWindow;
}

function subscribeToHistory(onChange: () => void): () => void {
  window.addEventListener('popstate', onChange);
  return () => window.removeEventListener('popstate', onChange);
}

function readWindowSearch(): string {
  return window.location.search;
}

function readServerSearch(): string {
  return '';
}

function setWindowSearchParams(next: QfSearchParamsUpdate, options?: QfNavigateOptions): void {
  if (typeof window === 'undefined') return;
  const current = new URLSearchParams(window.location.search);
  const params = typeof next === 'function' ? next(current) : next;
  const query = params.toString();
  const url = `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`;
  if (options?.replace) window.history.replaceState(options.state ?? null, '', url);
  else window.history.pushState(options?.state ?? null, '', url);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

function useWindowSearchParams(): [URLSearchParams, QfSetSearchParams] {
  const search = useSyncExternalStore(subscribeToHistory, readWindowSearch, readServerSearch);
  const params = useMemo(() => new URLSearchParams(search), [search]);
  return [params, setWindowSearchParams];
}

const ANCHOR_ROUTER_ADAPTER: QfResolvedRouterAdapter = {
  Link: AnchorRouteLink,
  usePathname: useWindowPathname,
  useNavigate: useWindowNavigate,
  useSearchParams: useWindowSearchParams,
};

// --------------------------------------------------------------------------- #
// Context
// --------------------------------------------------------------------------- #

const QfRouterContext = createContext<QfResolvedRouterAdapter>(ANCHOR_ROUTER_ADAPTER);

export function QfRouterProvider({ adapter, children }: QfRouterProviderProps) {
  const resolved = useMemo<QfResolvedRouterAdapter>(
    () => ({
      Link: adapter.Link,
      usePathname: adapter.usePathname,
      useNavigate: adapter.useNavigate ?? ANCHOR_ROUTER_ADAPTER.useNavigate,
      useSearchParams: adapter.useSearchParams ?? ANCHOR_ROUTER_ADAPTER.useSearchParams,
    }),
    [adapter],
  );
  return <QfRouterContext.Provider value={resolved}>{children}</QfRouterContext.Provider>;
}

export function useQfRouter(): QfResolvedRouterAdapter {
  return useContext(QfRouterContext);
}

/** True when `pathname` is `to` (exact) or sits below it (non-exact). */
export function isRouteActive(pathname: string, to: string, end: boolean): boolean {
  const normalize = (path: string) => (path.length > 1 ? path.replace(/\/+$/, '') : path);
  const current = normalize(pathname);
  const target = normalize(to);
  if (current === target) return true;
  if (end) return false;
  return target === '/' || current.startsWith(`${target}/`);
}
