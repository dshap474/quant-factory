/**
 * Text primitive: size/weight/tone props plus named typographic variants.
 *
 * USAGE:
 *   <Text tone="muted" size="xs">…</Text>
 *   <Text variant="eyebrow">Signals</Text>
 *   <Text variant="caption" as="p" className="mt-2">Updated hourly.</Text>
 *   <Text variant="data">0.0312</Text>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ElementType, ReactNode } from 'react';

import { cn } from '../lib/cn';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export type TextVariant = 'body' | 'eyebrow' | 'label' | 'caption' | 'data';
export type TextSize = '2xs' | 'xs' | 'sm' | 'base' | 'lg';
export type TextWeight = 'normal' | 'medium' | 'semibold' | 'bold';
export type TextTone = 'default' | 'muted' | 'accent';

export interface TextProps {
  as?: ElementType;
  /** Named recipe; explicit size/weight/tone/mono props override its defaults. */
  variant?: TextVariant;
  size?: TextSize;
  weight?: TextWeight;
  tone?: TextTone;
  mono?: boolean;
  className?: string;
  children: ReactNode;
}

interface VariantRecipe {
  size: TextSize;
  weight: TextWeight;
  tone: TextTone;
  mono: boolean;
  /** Utilities the size/weight/tone axes cannot express. */
  extra?: string;
}

// --------------------------------------------------------------------------- #
// Recipes
// --------------------------------------------------------------------------- #

const SIZES: Record<TextSize, string> = {
  '2xs': 'text-caption',
  xs: 'text-caption',
  sm: 'text-body',
  base: 'text-section',
  lg: 'text-title',
};
const WEIGHTS: Record<TextWeight, string> = {
  normal: 'font-normal',
  medium: 'font-medium',
  semibold: 'font-semibold',
  bold: 'font-semibold',
};
const TONES: Record<TextTone, string> = {
  default: 'text-foreground',
  muted: 'text-muted-foreground',
  accent: 'text-foreground',
};
const VARIANTS: Record<TextVariant, VariantRecipe> = {
  body: { size: 'base', weight: 'normal', tone: 'default', mono: false },
  eyebrow: { size: 'xs', weight: 'medium', tone: 'muted', mono: false },
  label: { size: 'xs', weight: 'medium', tone: 'muted', mono: false },
  caption: { size: 'xs', weight: 'normal', tone: 'muted', mono: false },
  data: {
    size: 'xs',
    weight: 'normal',
    tone: 'default',
    mono: false,
    extra: 'tabular-nums',
  },
};

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Text({
  as: Tag = 'span',
  variant = 'body',
  size,
  weight,
  tone,
  mono,
  className,
  children,
}: TextProps) {
  const recipe = VARIANTS[variant];
  return (
    <Tag
      className={cn(
        SIZES[size ?? recipe.size],
        WEIGHTS[weight ?? recipe.weight],
        TONES[tone ?? recipe.tone],
        (mono ?? recipe.mono) && 'font-mono',
        recipe.extra,
        className,
      )}
    >
      {children}
    </Tag>
  );
}
