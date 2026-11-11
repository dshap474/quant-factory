/**
 * Compact bottom-bar search action; opened, its field fills the navigator's bottom bar.
 *
 * USAGE:
 *   <NavigatorSearch
 *     id="signal-search"
 *     label="Search signals"
 *     placeholder="Search signals"
 *     value={query}
 *     onChange={setQuery}
 *   />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Search } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { ICON_SIZE, ICON_STROKE } from '../lib/icon';
import { Button } from '../primitives/Button';
import { Input } from '../primitives/Input';

import './NavigatorSearch.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

interface NavigatorSearchProps {
  id: string;
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function NavigatorSearch({ id, label, placeholder, value, onChange }: NavigatorSearchProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const popoverId = `${id}-popover`;

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('pointerdown', handlePointerDown);
    inputRef.current?.focus();

    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
    };
  }, [open]);

  const closeAndRestoreFocus = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  return (
    <div className="navigator-search" ref={rootRef}>
      <Button
        ref={triggerRef}
        type="button"
        className="navigator-search-trigger"
        aria-label={label}
        aria-expanded={open}
        aria-controls={popoverId}
        data-has-query={value.length > 0 ? 'true' : 'false'}
        onClick={() => {
          setOpen((value) => !value);
        }}
      >
        <Search size={ICON_SIZE} strokeWidth={ICON_STROKE} aria-hidden="true" />
      </Button>
      {open ? (
        <search className="navigator-search-popover" id={popoverId}>
          <Input
            ref={inputRef}
            id={id}
            type="search"
            aria-label={label}
            value={value}
            onChange={(event) => {
              onChange(event.target.value);
            }}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                event.preventDefault();
                closeAndRestoreFocus();
              }
            }}
            placeholder={placeholder}
            autoComplete="off"
          />
        </search>
      ) : null}
    </div>
  );
}
