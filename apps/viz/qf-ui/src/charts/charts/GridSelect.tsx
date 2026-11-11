/**
 * Internal keyboard-accessible listbox for OptimizerGrid controls.
 *
 * USAGE:
 *   <GridSelect id="metric" value={value} options={options} onChange={setValue} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { ChevronDown } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import styles from './OptimizerGrid.module.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface GridSelectOption {
  value: string;
  label: string;
}
export interface GridSelectProps {
  id: string;
  value: string;
  options: readonly GridSelectOption[];
  onChange: (value: string) => void;
}

function wrappedIndex(index: number, length: number): number {
  return (index + length) % length;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function GridSelect({ id, value, options, onChange }: GridSelectProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const selectedIndex = Math.max(
    0,
    options.findIndex((option) => option.value === value),
  );
  const selected = options[selectedIndex];
  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', closeOutside);
    optionRefs.current[selectedIndex]?.focus();
    return () => document.removeEventListener('pointerdown', closeOutside);
  }, [open, selectedIndex]);
  const closeAndFocus = () => {
    setOpen(false);
    requestAnimationFrame(() => triggerRef.current?.focus());
  };
  const choose = (next: string) => {
    onChange(next);
    closeAndFocus();
  };
  const focusOption = (index: number) => {
    if (options.length > 0) optionRefs.current[wrappedIndex(index, options.length)]?.focus();
  };
  return (
    <div ref={rootRef} className={styles.select}>
      <button
        ref={triggerRef}
        id={id}
        type="button"
        className={styles.selectTrigger}
        role="combobox"
        aria-controls={`${id}-listbox`}
        aria-expanded={open}
        aria-haspopup="listbox"
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span>{selected?.label ?? value}</span>
        <ChevronDown aria-hidden="true" size={16} strokeWidth={1.8} />
      </button>
      {open ? (
        <div id={`${id}-listbox`} className={styles.selectList} role="listbox">
          {options.map((option, index) => (
            <button
              key={option.value}
              ref={(node) => {
                optionRefs.current[index] = node;
              }}
              type="button"
              className={styles.selectOption}
              role="option"
              aria-selected={option.value === value}
              tabIndex={option.value === value ? 0 : -1}
              onClick={() => choose(option.value)}
              onKeyDown={(event) => {
                if (event.key === 'ArrowDown') {
                  event.preventDefault();
                  focusOption(index + 1);
                } else if (event.key === 'ArrowUp') {
                  event.preventDefault();
                  focusOption(index - 1);
                } else if (event.key === 'Home') {
                  event.preventDefault();
                  focusOption(0);
                } else if (event.key === 'End') {
                  event.preventDefault();
                  focusOption(options.length - 1);
                } else if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  choose(option.value);
                } else if (event.key === 'Escape') {
                  event.preventDefault();
                  closeAndFocus();
                }
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
