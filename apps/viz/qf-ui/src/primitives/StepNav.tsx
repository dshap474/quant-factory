/**
 * Ordered step navigator: numbered markers joined by a rail, one title per step, and the
 * selected step marked with `aria-current`. Reads as a pipeline, not a flat list.
 *
 * USAGE:
 *   <StepNav
 *     label="Prompt stages"
 *     steps={[{ id: 'a', marker: '1', title: 'Analyze chapter' }, { id: 'm', marker: 'M', title: 'Meta' }]}
 *     selectedId={selected}
 *     onSelect={setSelected}
 *   />
 *   <StepNav orientation="horizontal" … />  // one row above a document, joined by short rules
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import { cn } from '../lib/cn';

import './StepNav.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface StepNavItem {
  id: string;
  /** Short marker drawn in the step's circle: a number or one letter. */
  marker: ReactNode;
  title: ReactNode;
  /** Optional muted line under the title. */
  detail?: ReactNode;
}

export interface StepNavProps {
  label: string;
  steps: StepNavItem[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** `vertical` (default) stacks steps on a rail; `horizontal` sets them in one wrapping row. */
  orientation?: 'vertical' | 'horizontal';
  className?: string;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function StepNav({
  label,
  steps,
  selectedId,
  onSelect,
  orientation = 'vertical',
  className,
}: StepNavProps) {
  return (
    <nav aria-label={label} data-orientation={orientation} className={cn('ui-step-nav', className)}>
      <ol className="ui-step-nav-list">
        {steps.map((step) => {
          const selected = step.id === selectedId;
          return (
            <li key={step.id} className="ui-step-nav-item">
              <button
                type="button"
                className={cn('ui-step-nav-button', selected && 'is-selected')}
                aria-current={selected ? 'step' : undefined}
                onClick={() => onSelect(step.id)}
              >
                <span className="ui-step-nav-marker" aria-hidden="true">
                  {step.marker}
                </span>
                <span className="ui-step-nav-text">
                  <span className="ui-step-nav-title">{step.title}</span>
                  {step.detail ? <span className="ui-step-nav-detail">{step.detail}</span> : null}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
