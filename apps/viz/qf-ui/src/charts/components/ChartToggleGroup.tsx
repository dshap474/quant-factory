/**
 * Single-select chart-toolbar choice, drawn as a joined rail or a dropdown chip.
 *
 * Every chart-toolbar choice (transform windows, range pickers, ...) renders through
 * this group so all chart toolbars share one look:
 *   - 'rail' (default): one hairline-bordered bar per group, a caption segment, then
 *     every option as a joined segment. One click per option.
 *   - 'menu': one chip that reads out the current value and opens a short list. For
 *     long toolbars where a rail per group would not fit.
 *
 * USAGE:
 *   <ChartToggleGroup
 *     ariaLabel="Observation window"
 *     options={[{ value: '1y', label: '1Y' }, { value: '5y', label: '5Y' }]}
 *     value={range}
 *     onChange={setRange}
 *   />
 *   <ChartToggleGroup variant="menu" label="Z" allowDeselect ariaLabel="Z-score window" ... />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { ChevronDown } from 'lucide-react';
import {
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';

import './ChartToggleGroup.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

/** How a chart-toolbar choice is drawn. */
export type ChartToolbarVariant = 'rail' | 'menu';

export interface ChartToggleOption<T extends string | number> {
  value: T;
  label: ReactNode;
  /** Accessible name when the visible label is terse; defaults to the label text. */
  ariaLabel?: string;
  /** Tooltip; defaults to the accessible name. */
  title?: string;
}

interface ChartToggleGroupBaseProps<T extends string | number> {
  options: readonly ChartToggleOption<T>[];
  /** Accessible name for the whole group. */
  ariaLabel: string;
  /** Caption drawn ahead of the options (e.g. "Z", "EMA"); the chip's name in 'menu'. */
  label?: ReactNode;
  variant?: ChartToolbarVariant;
}

interface ChartToggleGroupRequiredProps<T extends string | number>
  extends ChartToggleGroupBaseProps<T> {
  /** Pressing the active option keeps it selected. */
  allowDeselect?: false;
  value: T;
  onChange: (value: T) => void;
}

interface ChartToggleGroupDeselectableProps<T extends string | number>
  extends ChartToggleGroupBaseProps<T> {
  /** Pressing the active option clears the selection; the menu gains an "Off" entry. */
  allowDeselect: true;
  value: T | null;
  onChange: (value: T | null) => void;
}

export type ChartToggleGroupProps<T extends string | number> =
  | ChartToggleGroupRequiredProps<T>
  | ChartToggleGroupDeselectableProps<T>;

interface ThumbPosition {
  left: number;
  width: number;
}

interface MenuPosition {
  left: number;
  top: number;
  minWidth: number;
}

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

const OFF_LABEL = 'Off';
const MENU_GAP = 4;
const VIEWPORT_PADDING = 8;

// --------------------------------------------------------------------------- #
// Rail
// --------------------------------------------------------------------------- #

function ChartToggleRail<T extends string | number>(props: ChartToggleGroupProps<T>) {
  const { options, ariaLabel, label, value } = props;
  const trackRef = useRef<HTMLDivElement>(null);
  const [thumb, setThumb] = useState<ThumbPosition | null>(null);
  const selectedIndex = options.findIndex((option) => option.value === value);
  const select = (option: T, pressed: boolean) => {
    if (props.allowDeselect) props.onChange(pressed ? null : option);
    else if (!pressed) props.onChange(option);
  };

  // The thumb is one element that slides to the pressed segment; re-measured on resize
  // so late font loads and wrapping toolbars keep it aligned.
  useLayoutEffect(() => {
    const track = trackRef.current;
    if (!track) return undefined;
    const measure = () => {
      const button = track.querySelectorAll<HTMLElement>('.qf-chart-toggle')[selectedIndex];
      setThumb(button ? { left: button.offsetLeft, width: button.offsetWidth } : null);
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(track);
    return () => observer.disconnect();
  }, [selectedIndex]);

  return (
    <fieldset className="qf-chart-toggle-group" data-variant="rail" aria-label={ariaLabel}>
      {label != null ? (
        <span className="qf-chart-toggle-group-label" aria-hidden="true">
          {label}
        </span>
      ) : null}
      <div ref={trackRef} className="qf-chart-toggle-track">
        {thumb ? (
          <span
            className="qf-chart-toggle-thumb"
            aria-hidden="true"
            style={{ transform: `translateX(${thumb.left}px)`, width: thumb.width }}
          />
        ) : null}
        {options.map((option) => {
          const pressed = value === option.value;
          const name = option.ariaLabel;
          const title =
            option.title ??
            (name && props.allowDeselect ? `${pressed ? 'Disable' : 'Enable'} ${name}` : name);
          return (
            <button
              key={option.value}
              type="button"
              className="qf-chart-toggle"
              aria-label={name}
              aria-pressed={pressed}
              title={title}
              onClick={() => select(option.value, pressed)}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

// --------------------------------------------------------------------------- #
// Menu
// --------------------------------------------------------------------------- #

function menuPosition(trigger: HTMLElement): MenuPosition {
  const bounds = trigger.getBoundingClientRect();
  const minWidth = Math.max(bounds.width, 96);
  const left = Math.min(
    Math.max(bounds.right - minWidth, VIEWPORT_PADDING),
    window.innerWidth - minWidth - VIEWPORT_PADDING,
  );
  return { left, top: bounds.bottom + MENU_GAP, minWidth };
}

function ChartToggleMenu<T extends string | number>(props: ChartToggleGroupProps<T>) {
  const { options, ariaLabel, label, value } = props;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<MenuPosition | null>(null);
  const menuId = useId();
  const open = position !== null;
  const selected = options.find((option) => option.value === value);
  const entries: { value: T | null; label: ReactNode; ariaLabel?: string }[] = [
    ...(props.allowDeselect
      ? [{ value: null, label: OFF_LABEL, ariaLabel: `${ariaLabel} off` }]
      : []),
    ...options,
  ];

  const close = (refocus: boolean) => {
    setPosition(null);
    if (refocus) triggerRef.current?.focus();
  };
  const choose = (next: T | null) => {
    if (props.allowDeselect) props.onChange(next);
    else if (next !== null) props.onChange(next);
    close(true);
  };

  useLayoutEffect(() => {
    if (!open) return;
    const items = menuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]');
    const checked = menuRef.current?.querySelector<HTMLButtonElement>('[aria-checked="true"]');
    (checked ?? items?.[0])?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const dismiss = (event: Event) => {
      const target = event.target as Node | null;
      if (target && (menuRef.current?.contains(target) || triggerRef.current?.contains(target))) {
        return;
      }
      setPosition(null);
    };
    const reposition = () => setPosition(null);
    document.addEventListener('pointerdown', dismiss, true);
    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', reposition, true);
    return () => {
      document.removeEventListener('pointerdown', dismiss, true);
      window.removeEventListener('resize', reposition);
      window.removeEventListener('scroll', reposition, true);
    };
  }, [open]);

  const onMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const items = [
      ...(menuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]') ?? []),
    ];
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === 'Escape' || event.key === 'Tab') {
      event.preventDefault();
      close(true);
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      items[(index + step + items.length) % items.length]?.focus();
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault();
      items[event.key === 'Home' ? 0 : items.length - 1]?.focus();
    }
  };

  const active = selected !== undefined;
  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="qf-chart-toggle-menu-trigger"
        data-active={active}
        aria-label={`${ariaLabel}: ${selected?.ariaLabel ?? (active ? String(value) : OFF_LABEL)}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => {
          if (open) close(false);
          else if (triggerRef.current) setPosition(menuPosition(triggerRef.current));
        }}
        onKeyDown={(event) => {
          if (event.key !== 'ArrowDown' || open || !triggerRef.current) return;
          event.preventDefault();
          setPosition(menuPosition(triggerRef.current));
        }}
      >
        {label != null ? <span className="qf-chart-toggle-menu-name">{label}</span> : null}
        <span className="qf-chart-toggle-menu-value">{selected?.label ?? OFF_LABEL}</span>
        <ChevronDown size={12} strokeWidth={1.8} aria-hidden="true" />
      </button>
      {position && typeof document !== 'undefined'
        ? createPortal(
            <div
              ref={menuRef}
              id={menuId}
              className="qf-chart-toggle-menu"
              role="menu"
              aria-label={ariaLabel}
              style={position}
              onKeyDown={onMenuKeyDown}
            >
              {entries.map((entry) => (
                <button
                  key={entry.value ?? '__off__'}
                  type="button"
                  role="menuitemradio"
                  className="qf-chart-toggle-menu-item"
                  aria-checked={entry.value === value || (entry.value === null && !active)}
                  aria-label={entry.ariaLabel}
                  tabIndex={-1}
                  onClick={() => choose(entry.value)}
                >
                  {entry.label}
                </button>
              ))}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ChartToggleGroup<T extends string | number>(props: ChartToggleGroupProps<T>) {
  return props.variant === 'menu' ? <ChartToggleMenu {...props} /> : <ChartToggleRail {...props} />;
}
