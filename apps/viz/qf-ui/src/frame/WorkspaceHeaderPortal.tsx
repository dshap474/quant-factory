/**
 * Portal route headers into the nearest app or section workspace header rail.
 *
 * USAGE:
 *   <WorkspaceHeaderTargetProvider target={target}>…</WorkspaceHeaderTargetProvider>
 *   <WorkspaceHeaderPortal><header>…</header></WorkspaceHeaderPortal>
 *   <WorkspaceToolbarTargetProvider target={target}>…</WorkspaceToolbarTargetProvider>
 *   <WorkspaceToolbarPortal><div>…</div></WorkspaceToolbarPortal>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { createContext, type ReactNode, useContext } from 'react';
import { createPortal } from 'react-dom';

// --------------------------------------------------------------------------- #
// Context
// --------------------------------------------------------------------------- #

const WorkspaceHeaderTargetContext = createContext<HTMLElement | null | undefined>(undefined);
const WorkspaceToolbarTargetContext = createContext<HTMLElement | null | undefined>(undefined);

// --------------------------------------------------------------------------- #
// Components
// --------------------------------------------------------------------------- #

export function WorkspaceHeaderTargetProvider({
  target,
  children,
}: {
  target: HTMLElement | null;
  children: ReactNode;
}) {
  return (
    <WorkspaceHeaderTargetContext.Provider value={target}>
      {children}
    </WorkspaceHeaderTargetContext.Provider>
  );
}

export function WorkspaceHeaderPortal({ children }: { children: ReactNode }) {
  const target = useContext(WorkspaceHeaderTargetContext);

  if (target === undefined) return children;
  if (target === null) return null;
  return createPortal(children, target);
}

export function WorkspaceToolbarTargetProvider({
  target,
  children,
}: {
  target: HTMLElement | null;
  children: ReactNode;
}) {
  return (
    <WorkspaceToolbarTargetContext.Provider value={target}>
      {children}
    </WorkspaceToolbarTargetContext.Provider>
  );
}

export function WorkspaceToolbarPortal({ children }: { children: ReactNode }) {
  const target = useContext(WorkspaceToolbarTargetContext);

  if (target === undefined) return children;
  if (target === null) return null;
  return createPortal(children, target);
}
