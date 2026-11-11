/**
 * Router-aware tab strip: one control-shaped route link per item (via the router adapter).
 *
 * Looks like SegmentedControl's `tabs` variant: bare text, a ghost pill on
 * hover, and the shared brand underline (useTabIndicator) sliding to the
 * current route, which is marked with `aria-current="page"`. Inside a page header the
 * tabs that do not fit fold into a More menu (tab-overflow.tsx).
 *
 * USAGE:
 *   <RouteTabs label="Example pages" items={[{ label: 'Overview', to: '/x' }]} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { useLayoutEffect, useRef } from 'react';

import { cn } from '../lib/cn';
import { isRouteActive, useQfRouter } from '../router/RouterAdapter';

import { revealInStrip, useTabIndicator } from './SegmentedControl';
import { TabOverflowMore, useTabOverflow } from './tab-overflow';
import './RouteTabs.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface RouteTabItem {
  label: string;
  to: string;
  /** exact match; default true */
  end?: boolean;
}

export interface RouteTabsProps {
  /** aria-label of the nav */
  label: string;
  items: readonly RouteTabItem[];
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function RouteTabs({ label, items, className }: RouteTabsProps) {
  const stripRef = useRef<HTMLElement | null>(null);
  const { Link, usePathname } = useQfRouter();
  const pathname = usePathname();

  // biome-ignore lint/correctness/useExhaustiveDependencies: the active tab moves when the pathname changes, so re-reveal it then.
  useLayoutEffect(() => {
    revealInStrip(stripRef.current?.querySelector<HTMLElement>('.active'));
  }, [pathname]);
  const activeIndex = items.findIndex((item) => isRouteActive(pathname, item.to, item.end ?? true));
  const folded = useTabOverflow(stripRef, items.length, activeIndex);
  useTabIndicator(stripRef, `${pathname} ${folded.join()}`);

  return (
    <nav ref={stripRef} className={cn('ui-route-tabs', className)} aria-label={label}>
      {items.map((item, index) => {
        const active = index === activeIndex;
        return (
          <Link
            key={item.to}
            to={item.to}
            data-tab-index={index}
            hidden={folded.includes(index)}
            aria-current={active ? 'page' : undefined}
            className={cn('ui-link ui-route-tabs-item', active && 'active')}
          >
            {item.label}
          </Link>
        );
      })}
      <TabOverflowMore
        items={items.flatMap((item, index) =>
          folded.includes(index) ? [{ key: item.to, label: item.label, to: item.to }] : [],
        )}
      />
      <span className="ui-tabs-indicator" aria-hidden="true" />
    </nav>
  );
}
