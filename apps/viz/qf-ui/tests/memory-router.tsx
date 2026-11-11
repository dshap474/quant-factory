/**
 * Router-free stand-in for tests: an in-memory qf-ui router adapter. Links render
 * anchors that navigate in memory on a plain left click; `useNavigate` and
 * `useSearchParams` update the same in-memory location.
 *
 * USAGE:
 *   import { LocationProbe, MemoryRouter } from '../../tests/memory-router';
 *   render(<MemoryRouter initialPath="/x/assets"><RouteTabs … /></MemoryRouter>);
 *   render(<MemoryRouter initialPath="/signals?q=a"><LocationProbe /><Navigator … /></MemoryRouter>);
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import {
  createContext,
  type MouseEvent,
  type ReactNode,
  useContext,
  useMemo,
  useState,
} from 'react';

import {
  type QfNavigate,
  type QfRouteLinkProps,
  type QfRouterAdapter,
  QfRouterProvider,
  type QfSetSearchParams,
  useQfRouter,
} from '../src/router/RouterAdapter';

// --------------------------------------------------------------------------- #
// Memory location
// --------------------------------------------------------------------------- #

interface MemoryLocation {
  pathname: string;
  search: string;
  navigate: QfNavigate;
  setSearch: QfSetSearchParams;
}

const MemoryLocationContext = createContext<MemoryLocation | null>(null);

function useMemoryLocation(): MemoryLocation {
  const location = useContext(MemoryLocationContext);
  if (!location) throw new Error('MemoryRouter missing');
  return location;
}

function splitPath(path: string): [string, string] {
  const index = path.indexOf('?');
  return index < 0 ? [path, ''] : [path.slice(0, index), path.slice(index + 1)];
}

// --------------------------------------------------------------------------- #
// Adapter
// --------------------------------------------------------------------------- #

function TestRouteLink({ to, state: _state, onClick, ...rest }: QfRouteLinkProps) {
  const { navigate } = useMemoryLocation();
  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    if (event.defaultPrevented || event.button !== 0) return;
    event.preventDefault();
    navigate(to);
  };
  return <a href={to} data-router-link="" onClick={handleClick} {...rest} />;
}

const TEST_ADAPTER: QfRouterAdapter = {
  Link: TestRouteLink,
  usePathname: () => useMemoryLocation().pathname,
  useNavigate: () => useMemoryLocation().navigate,
  useSearchParams: () => {
    const { search, setSearch } = useMemoryLocation();
    const params = useMemo(() => new URLSearchParams(search), [search]);
    return [params, setSearch];
  },
};

// --------------------------------------------------------------------------- #
// Components
// --------------------------------------------------------------------------- #

export interface MemoryRouterProps {
  initialPath?: string;
  children: ReactNode;
}

export function MemoryRouter({ initialPath = '/', children }: MemoryRouterProps) {
  const [initialPathname, initialSearch] = splitPath(initialPath);
  const [pathname, setPathname] = useState(initialPathname);
  const [search, setSearchString] = useState(initialSearch);
  const location: MemoryLocation = {
    pathname,
    search,
    navigate: (to) => {
      const [nextPathname, nextSearch] = splitPath(to);
      setPathname(nextPathname);
      setSearchString(nextSearch);
    },
    setSearch: (next) => {
      setSearchString((current) => {
        const params = typeof next === 'function' ? next(new URLSearchParams(current)) : next;
        return params.toString();
      });
    },
  };
  return (
    <MemoryLocationContext.Provider value={location}>
      <QfRouterProvider adapter={TEST_ADAPTER}>{children}</QfRouterProvider>
    </MemoryLocationContext.Provider>
  );
}

/** Renders the in-memory location (pathname plus search) for assertions. */
export function LocationProbe() {
  const { usePathname } = useQfRouter();
  const { search } = useMemoryLocation();
  const pathname = usePathname();
  return <output data-testid="location">{search ? `${pathname}?${search}` : pathname}</output>;
}
