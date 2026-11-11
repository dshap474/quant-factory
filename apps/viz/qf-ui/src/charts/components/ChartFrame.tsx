/**
 * Reusable chart frame preserving Viz header, body, and footer geometry.
 *
 * USAGE:
 *   <ChartFrame title="Equity"><LineChart ... /></ChartFrame>
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { ComponentType, ReactNode } from 'react';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface ChartFrameProps {
  title?: ReactNode;
  /** Heading element rendered for `title`; default 3 keeps existing callers unchanged. */
  headingLevel?: 2 | 3 | 4;
  titleAccessory?: ReactNode;
  titlePrefix?: ReactNode;
  titlePrefixComponent?: ComponentType;
  subtitle?: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

function classes(...values: Array<string | undefined>): string {
  return values.filter(Boolean).join(' ');
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function ChartFrame({
  title,
  headingLevel = 3,
  titleAccessory,
  titlePrefix,
  titlePrefixComponent: TitlePrefixComponent,
  subtitle,
  actions,
  footer,
  children,
  className,
  bodyClassName,
}: ChartFrameProps) {
  const Heading = `h${headingLevel}` as 'h2' | 'h3' | 'h4';
  return (
    <section className={classes('qf-chart-frame', className)}>
      {TitlePrefixComponent || titlePrefix || title || titleAccessory || subtitle || actions ? (
        <div className="qf-chart-frame-header">
          <div className="qf-chart-frame-heading">
            {TitlePrefixComponent ? <TitlePrefixComponent /> : titlePrefix}
            <div className="qf-chart-frame-labels">
              {title ? <Heading className="qf-chart-frame-title">{title}</Heading> : null}
              {titleAccessory ? (
                <span className="qf-chart-frame-title-accessory">{titleAccessory}</span>
              ) : null}
              {subtitle ? <span className="qf-chart-frame-subtitle">{subtitle}</span> : null}
            </div>
          </div>
          {actions ? <div className="qf-chart-frame-actions">{actions}</div> : null}
        </div>
      ) : null}
      <div className={classes('qf-chart-frame-body', bodyClassName)}>{children}</div>
      {footer ? <div className="qf-chart-frame-footer">{footer}</div> : null}
    </section>
  );
}
