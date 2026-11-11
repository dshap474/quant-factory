/**
 * Formatted stat card with optional trend tone and detail line.
 *
 * USAGE:
 *   <StatCard label="Regime 1" value="42%" detail="120 periods" />
 *   <StatCard label="Best Sharpe" value={1.2} format="number" trend="up" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Surface } from './Surface';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface StatCardProps {
  label: string;
  value: React.ReactNode;
  detail?: React.ReactNode;
  format?: 'number' | 'percent' | 'currency' | 'raw';
  trend?: 'up' | 'down' | 'neutral';
}

// --------------------------------------------------------------------------- #
// Helpers
// --------------------------------------------------------------------------- #

function formatValue(value: React.ReactNode, format: StatCardProps['format']): React.ReactNode {
  if (typeof value !== 'number') return value;
  if (format === 'raw') return String(value);

  switch (format) {
    case 'percent':
      return `${(value * 100).toFixed(2)}%`;
    case 'currency':
      return `$${value.toLocaleString()}`;
    default:
      return Number.isInteger(value) ? value.toLocaleString('en-US') : value.toFixed(2);
  }
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function StatCard({
  label,
  value,
  detail,
  format = 'number',
  trend = 'neutral',
}: StatCardProps) {
  const tone =
    trend === 'up' ? 'text-positive' : trend === 'down' ? 'text-negative' : 'text-foreground';

  return (
    <Surface className="bg-card/70 p-4">
      <div className="mb-2 text-caption font-medium text-muted-foreground">{label}</div>
      <div className={`text-metric font-semibold tabular-nums ${tone}`}>
        {formatValue(value, format)}
      </div>
      {detail ? <div className="mt-1 text-caption text-muted-foreground">{detail}</div> : null}
    </Surface>
  );
}
