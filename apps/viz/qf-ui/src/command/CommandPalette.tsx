/**
 * Router-free ⌘K command palette: a cmdk `Command` (filterable, keyboard-navigable list)
 * inside a Base UI Dialog (focus trap, Escape, backdrop, portal). The host owns the open
 * state, the global shortcut, and what selecting an item does; this module owns the
 * surface. It pulls in cmdk and Base UI, so hosts should load it lazily on first open
 * (`@quant-factory/qf-ui/command` is the code-split entry).
 *
 * Selecting an item runs its `onSelect`, then asks the host to close via `onOpenChange(false)`.
 * The search text resets on every open because the popup unmounts when closed.
 *
 * USAGE:
 *   <CommandPalette
 *     open={open}
 *     onOpenChange={setOpen}
 *     groups={[
 *       {
 *         id: 'go',
 *         heading: 'Go to',
 *         items: [{ id: 'docs', label: 'Docs', hint: '/docs', onSelect: () => navigate('/docs') }],
 *       },
 *     ]}
 *   />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Dialog } from '@base-ui/react/dialog';
import { Command } from 'cmdk';
import { Search } from 'lucide-react';
import { ICON_SIZE, ICON_STROKE } from '../lib/icon';

import { Kbd, KbdGroup } from '../primitives/Kbd';

import './CommandPalette.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface CommandItem {
  /** Stable id, unique within its group. */
  id: string;
  label: string;
  /** Right-aligned muted mono text, e.g. the destination path. */
  hint?: string;
  /** Extra search terms that match without being displayed. */
  keywords?: readonly string[];
  onSelect: () => void;
}

export interface CommandGroup {
  /** Stable id, unique within the palette. */
  id: string;
  heading: string;
  items: readonly CommandItem[];
}

export interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  groups: readonly CommandGroup[];
  /** Input placeholder. Default 'Search…'. */
  placeholder?: string;
  /** Shown when no item matches the search. Default 'No results.'. */
  emptyLabel?: string;
  /** Accessible dialog title (visually hidden). Default 'Command menu'. */
  label?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function CommandPalette({
  open,
  onOpenChange,
  groups,
  placeholder = 'Search…',
  emptyLabel = 'No results.',
  label = 'Command menu',
}: CommandPaletteProps) {
  const select = (item: CommandItem) => {
    item.onSelect();
    onOpenChange(false);
  };

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
      }}
    >
      <Dialog.Portal>
        <Dialog.Backdrop className="ui-command-backdrop qf-motion-fade" />
        <Dialog.Popup className="ui-command-popup">
          <Dialog.Title className="sr-only">{label}</Dialog.Title>
          <Dialog.Description className="sr-only">
            Type to filter, use the arrow keys to move, and press Enter to select.
          </Dialog.Description>
          <Command className="ui-command" label={label} loop>
            <div className="ui-command-input-row">
              <Search size={ICON_SIZE} strokeWidth={ICON_STROKE} aria-hidden="true" />
              <Command.Input className="ui-command-input" placeholder={placeholder} />
            </div>
            <Command.List className="ui-command-list">
              <Command.Empty className="ui-command-empty">{emptyLabel}</Command.Empty>
              {groups.map((group) => (
                <Command.Group key={group.id} heading={group.heading}>
                  {group.items.map((item) => (
                    <Command.Item
                      key={item.id}
                      className="ui-command-item"
                      value={`${group.id}/${item.id}`}
                      keywords={[item.label, ...(item.keywords ?? [])]}
                      onSelect={() => {
                        select(item);
                      }}
                    >
                      <span className="ui-command-item-label">{item.label}</span>
                      {item.hint ? <span className="ui-command-item-hint">{item.hint}</span> : null}
                    </Command.Item>
                  ))}
                </Command.Group>
              ))}
            </Command.List>
          </Command>
          <div className="ui-command-footer">
            <span className="ui-command-footer-hint">
              <KbdGroup>
                <Kbd>↑</Kbd>
                <Kbd>↓</Kbd>
              </KbdGroup>
              navigate
            </span>
            <span className="ui-command-footer-hint">
              <Kbd>↵</Kbd>
              open
            </span>
            <span className="ui-command-footer-hint">
              <Kbd>esc</Kbd>
              close
            </span>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
