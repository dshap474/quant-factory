/**
 * Global ⌘K / Ctrl+K command menu. Lists every destination the sidebar and the
 * Dashboards navigator already know (primary sections, Docs, dashboards) and
 * navigates with the app router. The palette itself (cmdk + Base UI dialog) is
 * code-split and only fetched the first time the menu opens; the shortcut
 * listener is the only eager part.
 *
 * USAGE:
 *   // Mounted once inside the router by AppShell, which owns the open state:
 *   <CommandMenu open={open} onOpenChange={setOpen} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { type CommandGroup, isTypingTarget, lazyNamed } from '@quant-factory/qf-ui';
import { Suspense, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { dashboardDestinations } from '@/extensions';
import { DOCS_NAV_ITEM, primaryNavItems } from './Sidebar';

// --------------------------------------------------------------------------- #
// Lazy palette
// --------------------------------------------------------------------------- #

const CommandPalette = lazyNamed(() => import('@quant-factory/qf-ui/command'), 'CommandPalette');

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

/** Whether the event target is editable text that is not part of the palette itself. */
function isForeignTextField(target: EventTarget | null): boolean {
  return isTypingTarget(target) && !(target as HTMLElement).closest('[cmdk-root]');
}

/** Build the palette groups; `go` runs a router navigation. */
function buildCommandGroups(go: (path: string) => void): CommandGroup[] {
  const sections = [...primaryNavItems(), DOCS_NAV_ITEM].map((item) => ({
    id: item.href,
    label: item.label,
    hint: item.href,
    onSelect: () => {
      go(item.href);
    },
  }));
  const dashboards = dashboardDestinations().map((dashboard) => ({
    id: dashboard.path,
    label: dashboard.label,
    hint: dashboard.path,
    onSelect: () => {
      go(dashboard.path);
    },
  }));
  return [
    { id: 'sections', heading: 'Go to', items: sections },
    { id: 'dashboards', heading: 'Dashboards', items: dashboards },
  ];
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export interface CommandMenuProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CommandMenu({ open, onOpenChange }: CommandMenuProps) {
  const navigate = useNavigate();
  // The palette chunk is requested on first open and stays mounted afterwards.
  const [requested, setRequested] = useState(false);
  if (open && !requested) setRequested(true);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== 'k') return;
      if (!(event.metaKey || event.ctrlKey) || event.altKey || event.shiftKey) return;
      if (isForeignTextField(event.target)) return;
      event.preventDefault();
      onOpenChange(!open);
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open, onOpenChange]);

  const groups = useMemo(
    () =>
      buildCommandGroups((path) => {
        void navigate(path);
      }),
    [navigate],
  );

  if (!requested) return null;
  return (
    <Suspense fallback={null}>
      <CommandPalette
        open={open}
        onOpenChange={onOpenChange}
        groups={groups}
        placeholder="Go to…"
        emptyLabel="No matching destination."
      />
    </Suspense>
  );
}
