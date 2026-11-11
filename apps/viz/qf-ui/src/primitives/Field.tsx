/**
 * Shared label wrapper for stacked and inline form controls.
 *
 * USAGE:
 *   <Field label="Rows" htmlFor={id}><SelectControl id={id} options={options} /></Field>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ReactNode } from 'react';

import './Field.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface FieldProps {
  label: ReactNode;
  htmlFor: string;
  layout?: 'inline' | 'stacked';
  className?: string;
  children: ReactNode;
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function Field({ label, htmlFor, layout = 'stacked', className, children }: FieldProps) {
  return (
    <div
      className={[
        'ui-field',
        layout === 'inline' ? 'ui-field-inline' : 'ui-field-stacked',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <label className="ui-field-label" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
    </div>
  );
}
