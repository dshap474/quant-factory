/**
 * The command menu's keyboard shortcut as keycaps, matching the viewer's platform.
 *
 * USAGE:
 *   <CommandMenuShortcut />
 *   <button title={`Search pages (${COMMAND_MENU_SHORTCUT_LABEL})`} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Kbd, KbdGroup } from '@quant-factory/qf-ui';

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

const MODIFIER_KEY = /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘' : 'Ctrl';

export const COMMAND_MENU_SHORTCUT_LABEL = `${MODIFIER_KEY} K`;

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function CommandMenuShortcut({ className }: { className?: string }) {
  return (
    <KbdGroup className={className}>
      <Kbd>{MODIFIER_KEY}</Kbd>
      <Kbd>K</Kbd>
    </KbdGroup>
  );
}
