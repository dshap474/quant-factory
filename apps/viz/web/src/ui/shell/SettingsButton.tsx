/**
 * Sidebar settings popover for the theme and global preview row count.
 *
 * The popover body (and its Radix Select dependency) loads lazily on first
 * open; the fallback mirrors the loaded panel geometry so nothing shifts.
 *
 * USAGE:
 *   <SettingsButton collapsed={false} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Button, ICON_SIZE, ICON_STROKE, lazyNamed } from '@quant-factory/qf-ui';
import { Settings } from 'lucide-react';
import { Suspense, useEffect, useRef, useState } from 'react';

import './SettingsButton.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface SettingsButtonProps {
  collapsed?: boolean;
}

// --------------------------------------------------------------------------- #
// Lazy panel
// --------------------------------------------------------------------------- #

const SettingsPanel = lazyNamed(() => import('./SettingsPanel'), 'SettingsPanel');

function isInsideSelectContent(target: EventTarget | null): boolean {
  // Radix select options render in a body portal outside the popover root.
  return target instanceof Element && target.closest('[data-slot="select-content"]') !== null;
}

function SettingsPanelFallback() {
  return (
    <>
      <div className="settings-section">
        <div>
          <strong>Theme</strong>
          <span>Interface colours</span>
        </div>
        <div
          className="settings-control-placeholder motion-safe:animate-pulse"
          aria-hidden="true"
        />
      </div>
      <div className="settings-section">
        <div>
          <strong>Rows</strong>
          <span>Preview pagination</span>
        </div>
        <div
          className="settings-control-placeholder motion-safe:animate-pulse"
          aria-hidden="true"
        />
      </div>
    </>
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function SettingsButton({ collapsed = false }: SettingsButtonProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (rootRef.current?.contains(event.target as Node)) return;
      if (isInsideSelectContent(event.target)) return;
      setOpen(false);
    };
    document.addEventListener('pointerdown', handlePointerDown);

    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
    };
  }, [open]);

  const closeAndRestoreFocus = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  return (
    <div
      className="settings-wrap"
      ref={rootRef}
      onKeyDown={(event) => {
        if (event.key !== 'Escape' || !open) return;
        if (isInsideSelectContent(event.target)) return;
        event.preventDefault();
        event.stopPropagation();
        closeAndRestoreFocus();
      }}
    >
      <Button
        ref={triggerRef}
        type="button"
        className={collapsed ? 'settings-button collapsed' : 'settings-button'}
        aria-label="Open settings"
        aria-expanded={open}
        title="Settings"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="sidebar-control-icon-slot" aria-hidden="true">
          <Settings size={ICON_SIZE} strokeWidth={ICON_STROKE} />
        </span>
        {collapsed ? null : <span>Settings</span>}
      </Button>

      {open ? (
        <div className="settings-popover">
          <Suspense fallback={<SettingsPanelFallback />}>
            <SettingsPanel />
          </Suspense>
        </div>
      ) : null}
    </div>
  );
}
