/**
 * The folded-tabs menu behind a tab strip's More trigger. Loaded lazily by
 * tab-overflow.tsx; route tabs render as links, view tabs call `onSelect`.
 *
 * USAGE:
 *   <TabOverflowMenu items={[{ key: 'assets', label: 'Assets', to: '/x/assets' }]} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../overlay/DropdownMenu';
import { useQfRouter } from '../router/RouterAdapter';
import { Button } from './Button';
import { TabOverflowLabel } from './tab-overflow';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface TabOverflowMenuItem {
  key: string;
  label: ReactNode;
  /** Route tabs navigate; view tabs set `onSelect` instead. */
  to?: string | undefined;
  onSelect?: (() => void) | undefined;
  disabled?: boolean | undefined;
}

export interface TabOverflowMenuProps {
  items: TabOverflowMenuItem[];
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function TabOverflowMenu({ items }: TabOverflowMenuProps) {
  const { Link } = useQfRouter();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button className="ui-tabs-more" />}>
        <TabOverflowLabel />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {items.map((item) => (
          <DropdownMenuItem
            key={item.key}
            disabled={item.disabled ?? false}
            {...(item.to ? { render: <Link to={item.to} /> } : {})}
            {...(item.onSelect ? { onClick: item.onSelect } : {})}
          >
            {item.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
