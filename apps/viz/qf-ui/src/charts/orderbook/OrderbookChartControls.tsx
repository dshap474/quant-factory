/**
 * Portable UTC window navigation for orderbook chart hosts.
 * USAGE: <OrderbookChartControls start={start} first={first} last={last}
 *   hours={6} bandPercent={2} onStartChange={setStart}
 *   onHoursChange={setHours} onBandPercentChange={setBand} />
 */

// --------------------------------------------------------------------------- #
// Imports and contracts
// --------------------------------------------------------------------------- #

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useId, useState } from 'react';
import { Toolbar } from '../../layout/Toolbar';
import { ICON_SIZE, ICON_STROKE } from '../../lib/icon';
import { Button } from '../../primitives/Button';
import { Field } from '../../primitives/Field';
import { Input } from '../../primitives/Input';
import { SegmentedControl } from '../../primitives/SegmentedControl';
import { SelectControl } from '../../primitives/Select';
import { Text } from '../../primitives/Text';
import type { OrderbookScaleMode } from '../charts/OrderbookChart';
import './OrderbookChartControls.css';

export interface OrderbookChartControlsProps {
  start: number | null;
  first: number | null;
  last: number | null;
  hours: number;
  bandPercent: number;
  onStartChange: (start: number) => void;
  onHoursChange: (hours: number) => void;
  onBandPercentChange: (percent: number) => void;
  scaleMode?: OrderbookScaleMode;
  onScaleModeChange?: (mode: OrderbookScaleMode) => void;
}

// --------------------------------------------------------------------------- #
// UTC conversion
// --------------------------------------------------------------------------- #

function dateInput(timestamp: number | null): string {
  return timestamp === null ? '' : new Date(timestamp * 1000).toISOString().slice(0, 16);
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function OrderbookChartControls({
  start,
  first,
  last,
  hours,
  bandPercent,
  onStartChange,
  onHoursChange,
  onBandPercentChange,
  scaleMode = 'relative',
  onScaleModeChange,
}: OrderbookChartControlsProps) {
  const id = useId();
  const [draftStart, setDraftStart] = useState(start);
  const [draft, setDraft] = useState(() => dateInput(start));
  if (draftStart !== start) {
    setDraftStart(start);
    setDraft(dateInput(start));
  }
  const unavailable = start === null || first === null || last === null;
  return (
    <Toolbar aria-label="Orderbook chart controls">
      <form
        className="qf-orderbook-controls"
        onSubmit={(event) => {
          event.preventDefault();
          const value = new FormData(event.currentTarget).get('windowStart');
          const timestamp = typeof value === 'string' ? Date.parse(`${value}Z`) / 1000 : Number.NaN;
          if (
            Number.isFinite(timestamp) &&
            first !== null &&
            last !== null &&
            timestamp >= first &&
            timestamp <= last
          )
            onStartChange(timestamp);
        }}
      >
        <div className="qf-orderbook-window-controls">
          <Field label="Window start (UTC)" htmlFor={`${id}-start`}>
            <div className="qf-orderbook-jump">
              <Input
                id={`${id}-start`}
                name="windowStart"
                aria-label="Orderbook window start (UTC)"
                type="datetime-local"
                step={60}
                required
                min={dateInput(first)}
                max={dateInput(last)}
                value={draft}
                disabled={unavailable}
                onChange={(event) => setDraft(event.target.value)}
              />
              <Button type="submit" variant="control" disabled={unavailable || !draft}>
                Jump
              </Button>
            </div>
          </Field>
          <Field label="Window" htmlFor={`${id}-hours`}>
            <SelectControl
              id={`${id}-hours`}
              ariaLabel="Orderbook time window"
              value={String(hours)}
              options={[
                { value: '1', label: '1 hour' },
                { value: '3', label: '3 hours' },
                { value: '6', label: '6 hours' },
                { value: '24', label: '1D · 24 hours' },
              ]}
              onValueChange={(value) => onHoursChange(Number(value))}
            />
          </Field>
          <div className="qf-orderbook-navigation">
            <Button
              variant="control"
              icon
              aria-label="Previous window"
              title="Previous window"
              disabled={unavailable || start === first}
              onClick={() => {
                if (start !== null && first !== null)
                  onStartChange(Math.max(first, start - hours * 3600));
              }}
            >
              <ChevronLeft size={ICON_SIZE} strokeWidth={ICON_STROKE} aria-hidden="true" />
            </Button>
            <Button
              variant="control"
              icon
              aria-label="Next window"
              title="Next window"
              disabled={unavailable || (start ?? 0) + hours * 3600 > (last ?? 0)}
              onClick={() => {
                if (start !== null) onStartChange(start + hours * 3600);
              }}
            >
              <ChevronRight size={ICON_SIZE} strokeWidth={ICON_STROKE} aria-hidden="true" />
            </Button>
          </div>
        </div>
        <div className="qf-orderbook-display-controls">
          <Field label="Price range" htmlFor={`${id}-range`}>
            <SelectControl
              id={`${id}-range`}
              ariaLabel="Orderbook price range"
              value={String(bandPercent)}
              options={[
                { value: '1', label: '±1% of mid' },
                { value: '2', label: '±2% of mid' },
                { value: '5', label: '±5% of mid' },
                { value: '0', label: 'All stored levels' },
              ]}
              onValueChange={(value) => onBandPercentChange(Number(value))}
            />
          </Field>
          {onScaleModeChange ? (
            <div className="qf-orderbook-scale">
              <Text variant="caption" tone="muted">
                Scale
              </Text>
              <SegmentedControl<OrderbookScaleMode>
                ariaLabel="Orderbook size scale"
                value={scaleMode}
                options={[
                  { value: 'relative', label: 'Relative' },
                  { value: 'historical', label: 'Historical' },
                ]}
                onValueChange={onScaleModeChange}
              />
            </div>
          ) : null}
        </div>
      </form>
    </Toolbar>
  );
}
