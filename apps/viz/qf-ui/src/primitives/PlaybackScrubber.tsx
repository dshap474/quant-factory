/**
 * Timeline scrubber: transport (step back, Play/Pause, step forward), a range slider over
 * `count` positions whose index the host owns with the elapsed part filled, the current
 * position's label (usually its date) and a speed control. `sticky` pins it to the top of
 * the scrolling pane, so it stays in reach while the charts it drives scroll past.
 *
 * USAGE:
 *   const [index, setIndex] = useState(dates.length - 1);
 *   <PlaybackScrubber
 *     sticky
 *     ariaLabel="Replay position"
 *     count={dates.length}
 *     index={index}
 *     onIndexChange={setIndex}
 *     label={formatIsoDay(dates[index])}
 *   />
 *
 * Play advances so a full timeline takes about `durationMs` at 1x; it stops at the end and
 * restarts from the start when pressed there. Stepping or dragging pauses playback.
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import { Pause, Play, StepBack, StepForward } from 'lucide-react';
import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from 'react';

import { cn } from '../lib/cn';
import { Button } from './Button';
import { SegmentedControl } from './SegmentedControl';

import './PlaybackScrubber.css';

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface PlaybackScrubberProps {
  ariaLabel: string;
  /** Number of timeline positions; the slider spans 0..count-1. */
  count: number;
  index: number;
  onIndexChange: (index: number) => void;
  /** The current position, shown beside the slider and announced as its value. */
  label: ReactNode;
  /** Speed multipliers offered. Default [1, 5, 10]. */
  speeds?: readonly number[];
  /** Speed selected at mount; falls back to the first speed when not offered. Default 5. */
  defaultSpeed?: number;
  /** Milliseconds a full timeline takes at 1x. Default 60000. */
  durationMs?: number;
  /** Pin the bar to the top of its scrolling pane. */
  sticky?: boolean;
  className?: string;
}

// --------------------------------------------------------------------------- #
// Constants
// --------------------------------------------------------------------------- #

const DEFAULT_SPEEDS = [1, 5, 10] as const;
const DEFAULT_SPEED = 5;
const TICK_MS = 50;

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function PlaybackScrubber({
  ariaLabel,
  count,
  index,
  onIndexChange,
  label,
  speeds = DEFAULT_SPEEDS,
  defaultSpeed = DEFAULT_SPEED,
  durationMs = 60_000,
  sticky = false,
  className,
}: PlaybackScrubberProps) {
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(
    speeds.includes(defaultSpeed) ? defaultSpeed : (speeds[0] ?? 1),
  );
  const last = Math.max(count - 1, 0);
  const current = Math.min(index, last);
  // The interval reads the latest index and callback without restarting on every step.
  const state = useRef({ index, onIndexChange });
  state.current = { index, onIndexChange };

  useEffect(() => {
    if (!playing) return;
    // Fractional rows per tick, accumulated, so every speed holds its duration at any row count.
    const perTick = (last * TICK_MS * speed) / durationMs;
    let position = state.current.index;
    const timer = window.setInterval(() => {
      if (Math.floor(position) !== state.current.index) position = state.current.index; // dragged
      position = Math.min(position + perTick, last);
      const next = Math.floor(position);
      if (next !== state.current.index) state.current.onIndexChange(next);
      if (position >= last) setPlaying(false);
    }, TICK_MS);
    return () => window.clearInterval(timer);
  }, [playing, speed, last, durationMs]);

  const toggle = () => {
    if (!playing && index >= last) onIndexChange(0);
    setPlaying(!playing);
  };
  const step = (by: number) => {
    setPlaying(false);
    // From the latest index, so quick repeated steps each count.
    onIndexChange(Math.min(Math.max(Math.min(state.current.index, last) + by, 0), last));
  };
  const progress = last > 0 ? (current / last) * 100 : 0;

  return (
    <div className={cn('ui-playback', sticky && 'ui-playback--sticky', className)}>
      <div className="ui-playback-transport">
        <Button
          variant="plain"
          size="sm"
          icon
          aria-label="Step back"
          title="Step back"
          disabled={count < 2 || current <= 0}
          onClick={() => step(-1)}
        >
          <StepBack aria-hidden="true" />
        </Button>
        <Button
          variant="primary"
          size="sm"
          icon
          className="ui-playback-play"
          aria-label={playing ? 'Pause' : 'Play'}
          title={playing ? 'Pause' : 'Play'}
          aria-pressed={playing}
          disabled={count < 2}
          onClick={toggle}
        >
          {playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
        </Button>
        <Button
          variant="plain"
          size="sm"
          icon
          aria-label="Step forward"
          title="Step forward"
          disabled={count < 2 || current >= last}
          onClick={() => step(1)}
        >
          <StepForward aria-hidden="true" />
        </Button>
      </div>
      <input
        type="range"
        className="ui-playback-range"
        style={{ '--ui-playback-progress': `${progress}%` } as CSSProperties}
        aria-label={ariaLabel}
        aria-valuetext={typeof label === 'string' ? label : undefined}
        min={0}
        max={last}
        step={1}
        value={current}
        disabled={count < 2}
        onChange={(event) => {
          setPlaying(false);
          onIndexChange(Number(event.currentTarget.value));
        }}
      />
      <span className="ui-playback-label" aria-live="off">
        {label}
      </span>
      <SegmentedControl
        size="sm"
        ariaLabel="Playback speed"
        value={String(speed)}
        options={speeds.map((value) => ({ value: String(value), label: `${value}×` }))}
        onValueChange={(value) => setSpeed(Number(value))}
      />
    </div>
  );
}
