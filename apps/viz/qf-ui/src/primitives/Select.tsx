/**
 * Shared app select composition over Radix primitives.
 *
 * USAGE:
 *   <SelectControl value={value} onValueChange={setValue} options={options} />
 *   <SelectControl size="sm" value={value} onValueChange={setValue} options={options} />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import * as SelectPrimitive from '@radix-ui/react-select';
import { Check, ChevronDown, ChevronUp } from 'lucide-react';
import type { ComponentProps, ReactNode } from 'react';
import { cn } from '../lib/cn';
import { ICON_SIZE, ICON_STROKE } from '../lib/icon';
import { type ControlSize, controlSizeClass } from './control-size';

import './Select.css';

// --------------------------------------------------------------------------- #
// Values
// --------------------------------------------------------------------------- #

const EMPTY_SELECT_VALUE = '__qf_empty_select_value__';

function toPrimitiveValue(value: string | undefined): string | undefined {
  return value === '' ? EMPTY_SELECT_VALUE : value;
}

function fromPrimitiveValue(value: string): string {
  return value === EMPTY_SELECT_VALUE ? '' : value;
}

// --------------------------------------------------------------------------- #
// Shadcn primitives
// --------------------------------------------------------------------------- #

function Select({
  value,
  defaultValue,
  onValueChange,
  ...props
}: ComponentProps<typeof SelectPrimitive.Root>) {
  const primitiveValue = toPrimitiveValue(value);
  const primitiveDefaultValue = toPrimitiveValue(defaultValue);
  return (
    <SelectPrimitive.Root
      data-slot="select"
      {...(primitiveValue === undefined ? {} : { value: primitiveValue })}
      {...(primitiveDefaultValue === undefined ? {} : { defaultValue: primitiveDefaultValue })}
      onValueChange={(nextValue) => onValueChange?.(fromPrimitiveValue(nextValue))}
      {...props}
    />
  );
}

function SelectValue(props: ComponentProps<typeof SelectPrimitive.Value>) {
  return <SelectPrimitive.Value data-slot="select-value" {...props} />;
}

function SelectTrigger({
  className,
  children,
  ...props
}: ComponentProps<typeof SelectPrimitive.Trigger>) {
  return (
    <SelectPrimitive.Trigger
      data-slot="select-trigger"
      className={cn('ui-select-trigger', className)}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon asChild>
        <ChevronDown
          aria-hidden="true"
          className="ui-select-chevron"
          size={ICON_SIZE}
          strokeWidth={ICON_STROKE}
        />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  );
}

function SelectContent({
  className,
  children,
  position = 'item-aligned',
  ...props
}: ComponentProps<typeof SelectPrimitive.Content>) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content
        data-slot="select-content"
        className={cn('ui-select-content', className)}
        position={position}
        {...props}
      >
        <SelectScrollUpButton />
        <SelectPrimitive.Viewport data-slot="select-viewport" className="ui-select-viewport">
          {children}
        </SelectPrimitive.Viewport>
        <SelectScrollDownButton />
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  );
}

function SelectItem({
  className,
  children,
  value,
  ...props
}: ComponentProps<typeof SelectPrimitive.Item>) {
  return (
    <SelectPrimitive.Item
      data-slot="select-item"
      className={cn('ui-select-item', className)}
      value={toPrimitiveValue(value) ?? value}
      {...props}
    >
      <span data-slot="select-item-indicator" className="ui-select-item-indicator">
        <SelectPrimitive.ItemIndicator>
          <Check aria-hidden="true" size={ICON_SIZE} strokeWidth={ICON_STROKE} />
        </SelectPrimitive.ItemIndicator>
      </span>
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
    </SelectPrimitive.Item>
  );
}

function SelectScrollUpButton({
  className,
  ...props
}: ComponentProps<typeof SelectPrimitive.ScrollUpButton>) {
  return (
    <SelectPrimitive.ScrollUpButton
      data-slot="select-scroll-up-button"
      className={cn('ui-select-scroll-button', className)}
      {...props}
    >
      <ChevronUp aria-hidden="true" size={ICON_SIZE} strokeWidth={ICON_STROKE} />
    </SelectPrimitive.ScrollUpButton>
  );
}

function SelectScrollDownButton({
  className,
  ...props
}: ComponentProps<typeof SelectPrimitive.ScrollDownButton>) {
  return (
    <SelectPrimitive.ScrollDownButton
      data-slot="select-scroll-down-button"
      className={cn('ui-select-scroll-button', className)}
      {...props}
    >
      <ChevronDown aria-hidden="true" size={ICON_SIZE} strokeWidth={ICON_STROKE} />
    </SelectPrimitive.ScrollDownButton>
  );
}

// --------------------------------------------------------------------------- #
// Simple composition
// --------------------------------------------------------------------------- #

export interface SelectControlOption {
  value: string;
  label: ReactNode;
  disabled?: boolean;
}

export interface SelectControlProps
  extends Omit<ComponentProps<typeof SelectPrimitive.Root>, 'children'> {
  id?: string;
  className?: string;
  ariaLabel?: string;
  placeholder?: ReactNode;
  /** Trigger height step; 'xs' and 'sm' also tighten the type. Default 'md'. */
  size?: ControlSize;
  options: ReadonlyArray<SelectControlOption>;
}

export function SelectControl({
  id,
  className,
  ariaLabel,
  placeholder,
  size,
  options,
  value,
  ...props
}: SelectControlProps) {
  const selectedLabel =
    value === undefined ? undefined : options.find((option) => option.value === value)?.label;

  return (
    <Select {...(value === undefined ? {} : { value })} {...props}>
      <SelectTrigger
        id={id}
        className={cn(
          controlSizeClass(size),
          (size === 'sm' || size === 'xs') && 'is-sm',
          className,
        )}
        aria-label={ariaLabel}
      >
        <SelectValue placeholder={placeholder}>{selectedLabel}</SelectValue>
      </SelectTrigger>
      <SelectContent position="popper">
        {options.map((option) => (
          <SelectItem
            key={option.value}
            value={option.value}
            {...(option.disabled === undefined ? {} : { disabled: option.disabled })}
          >
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
