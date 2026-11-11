/**
 * Sole ECharts lifecycle owner for qf-charts.
 *
 * USAGE:
 *   <QfChart option={option} ariaLabel="Portfolio equity" />
 */

// --------------------------------------------------------------------------- #
// Imports
// --------------------------------------------------------------------------- #

import type { EChartsType } from 'echarts/core';
import * as echarts from 'echarts/core';
import {
  type CSSProperties,
  type KeyboardEventHandler,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';

import { type QfChartTheme, useChartTheme } from '../hooks/useChartTheme';
import { recordLifecycle } from './diagnostics/lifecycle';
import { QF_CHART_ASPECT_RATIO } from './geometry';
import { registerCharts } from './registerCharts';
import { qfEChartsTooltipChrome } from './tooltip';

import '../theme/qf-charts.css';

registerCharts();

// --------------------------------------------------------------------------- #
// Types
// --------------------------------------------------------------------------- #

export interface QfChartClickEvent {
  data?: unknown;
  dataIndex?: number;
  name?: string;
  seriesIndex?: number;
  value?: unknown;
}

export type QfChartOption = Readonly<Record<string, unknown>>;

export interface QfChartProps {
  option: QfChartOption;
  ariaLabel: string;
  height?: number | string | undefined;
  width?: number | string | undefined;
  className?: string | undefined;
  style?: CSSProperties | undefined;
  onClick?: ((event: QfChartClickEvent) => void) | undefined;
  onKeyDown?: KeyboardEventHandler<HTMLDivElement> | undefined;
  interactive?: boolean | undefined;
  /** Always merge new options into the live instance, even across a structure change. */
  preserveInteractionState?: boolean | undefined;
  ariaDescribedBy?: string | undefined;
  /**
   * Style-only series updates matched by `id`, merged after `option`. Frequent changes
   * (a hover fade) go here so ECharts never re-clones every series' data per frame.
   */
  seriesPatch?: readonly QfChartOption[] | undefined;
}

export { QF_CHART_ASPECT_RATIO } from './geometry';

// --------------------------------------------------------------------------- #
// Structural signature
// --------------------------------------------------------------------------- #

// Rule for resetting the instance: an option update replaces the chart (notMerge)
// only when its STRUCTURE changes — the identity, count, order, type or axis
// assignment of the series, or the number of axes / dataZoom components. When the
// structure is unchanged the option is merged, so state the user set by interacting
// with the chart (dataZoom window, tooltip pinning) survives a data or styling
// update. Dropping or reordering series changes the signature, so a preserved zoom
// can never resurrect a series the new option no longer contains.

function componentCount(value: unknown): number {
  return Array.isArray(value) ? value.length : value == null ? 0 : 1;
}

export function chartStructureSignature(option: QfChartOption): string {
  const series = option.series;
  const list = Array.isArray(series) ? series : series == null ? [] : [series];
  const seriesKeys = list.map((entry) => {
    const item = (entry ?? {}) as Record<string, unknown>;
    return [item.id ?? item.name ?? '', item.type ?? '', item.yAxisIndex ?? 0, item.xAxisIndex ?? 0]
      .map(String)
      .join('~');
  });
  return [
    seriesKeys.join('|'),
    `x:${componentCount(option.xAxis)}`,
    `y:${componentCount(option.yAxis)}`,
    `z:${componentCount(option.dataZoom)}`,
  ].join('#');
}

// --------------------------------------------------------------------------- #
// Base text style
// --------------------------------------------------------------------------- #

// ECharts draws canvas text in its own 12px sans-serif unless an option says
// otherwise. Every option without a textStyle gets the token sans in the axis label
// colour, so every renderer, including raw host options, draws chart text in one face.
export function withBaseTextStyle(option: QfChartOption, theme: QfChartTheme): QfChartOption {
  if (option.textStyle != null) return option;
  return {
    textStyle: { fontFamily: theme.fontFamily, fontSize: theme.axisFontSize, color: theme.axis },
    ...option,
  };
}

// A raw host option that declares a tooltip but no surface would get ECharts' white
// default box. It gets the qf tooltip chrome underneath its own keys instead; trigger,
// formatter, position and pointer stay exactly as the host wrote them.
export function withBaseTooltipChrome(option: QfChartOption, theme: QfChartTheme): QfChartOption {
  const tooltip = option.tooltip;
  if (tooltip == null || typeof tooltip !== 'object' || Array.isArray(tooltip)) return option;
  const host = tooltip as Record<string, unknown>;
  if (host.backgroundColor != null || host.className != null) return option;
  const chrome = qfEChartsTooltipChrome(theme);
  const hostText = (host.textStyle ?? {}) as Record<string, unknown>;
  return {
    ...option,
    tooltip: { ...chrome, ...host, textStyle: { ...chrome.textStyle, ...hostText } },
  };
}

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function QfChart({
  option,
  ariaLabel,
  height,
  width = '100%',
  className = '',
  style,
  onClick,
  onKeyDown,
  interactive = false,
  preserveInteractionState = false,
  ariaDescribedBy,
  seriesPatch,
}: QfChartProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const instanceRef = useRef<EChartsType | null>(null);
  const clickRef = useRef(onClick);
  const tooltipRef = useRef(option.tooltip);
  const structureRef = useRef<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [instanceGeneration, setInstanceGeneration] = useState(0);
  const [fontGeneration, setFontGeneration] = useState(0);
  const theme = useChartTheme();

  useLayoutEffect(() => {
    clickRef.current = onClick;
    tooltipRef.current = option.tooltip;
  });

  // biome-ignore lint/correctness/useExhaustiveDependencies: incrementing the generation explicitly retries a failed initialization.
  useLayoutEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let instance: EChartsType;
    try {
      instance = echarts.init(host, undefined, { renderer: 'canvas', useDirtyRect: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error(String(caught)));
      return;
    }
    instanceRef.current = instance;
    structureRef.current = null;
    setError(null);
    recordLifecycle('init');
    const handleClick = (event: unknown) => clickRef.current?.(event as QfChartClickEvent);
    // A portaled tooltip stays fixed while its source canvas scrolls. Hide that
    // stale readout until the next pointer event resolves its new chart position.
    const handleAncestorScroll = (event: Event) => {
      const tooltip = tooltipRef.current as
        | { appendTo?: unknown; appendToBody?: boolean }
        | undefined;
      if (!tooltip?.appendTo && !tooltip?.appendToBody) return;
      if (event.target instanceof Node && event.target.contains(host))
        instance.dispatchAction({ type: 'hideTip' });
    };
    instance.on('click', handleClick);
    host.ownerDocument.addEventListener('scroll', handleAncestorScroll, true);

    return () => {
      instance.off('click', handleClick);
      host.ownerDocument.removeEventListener('scroll', handleAncestorScroll, true);
      if (!instance.isDisposed()) {
        instance.dispose();
        recordLifecycle('dispose');
      }
      if (instanceRef.current === instance) instanceRef.current = null;
    };
  }, [instanceGeneration]);

  const applyOption = useCallback(
    (instance: EChartsType) => {
      const structure = chartStructureSignature(option);
      const structureChanged = structureRef.current !== structure;
      structureRef.current = structure;
      try {
        instance.setOption(withBaseTooltipChrome(withBaseTextStyle(option, theme), theme), {
          notMerge: preserveInteractionState ? false : structureChanged,
        });
        setError(null);
        recordLifecycle('setOption');
      } catch (caught) {
        // A failed update may have left the instance half-applied, so the next
        // attempt replaces the option outright rather than merging into it.
        structureRef.current = null;
        setError(caught instanceof Error ? caught : new Error(String(caught)));
      }
    },
    [option, preserveInteractionState, theme],
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: the generations re-apply the current option to a recreated instance, or once the web font has loaded.
  useEffect(() => {
    const instance = instanceRef.current;
    if (!instance || instance.isDisposed()) return;
    applyOption(instance);
  }, [applyOption, instanceGeneration, fontGeneration]);

  // Runs after the option effect, so a re-applied option never wipes the current patch.
  // biome-ignore lint/correctness/useExhaustiveDependencies: applyOption changes with the option, which resets series styles; the patch re-applies on top.
  useEffect(() => {
    const instance = instanceRef.current;
    if (!seriesPatch || !instance || instance.isDisposed()) return;
    instance.setOption({ series: seriesPatch });
  }, [seriesPatch, applyOption]);

  // Canvas text drawn before the web font arrives stays in the fallback face until the
  // next update, so a chart mounted while fonts load re-applies its option once.
  useEffect(() => {
    const fonts = typeof document === 'undefined' ? undefined : document.fonts;
    if (fonts?.status !== 'loading') return;
    let cancelled = false;
    void fonts.ready.then(() => {
      if (!cancelled) setFontGeneration((value) => value + 1);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let frame: number | null = null;
    const observer = new ResizeObserver(() => {
      if (frame != null) cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        frame = null;
        const instance = instanceRef.current;
        if (!instance || instance.isDisposed()) return;
        instance.resize();
        recordLifecycle('resize');
      });
    });
    observer.observe(host);
    return () => {
      observer.disconnect();
      if (frame != null) cancelAnimationFrame(frame);
    };
  }, []);

  const retry = () => {
    const instance = instanceRef.current;
    if (!instance || instance.isDisposed()) {
      setInstanceGeneration((value) => value + 1);
      return;
    }
    applyOption(instance);
  };

  return (
    // biome-ignore lint/a11y/useAriaPropsSupportedByRole: runtime roles are img or button and both support an accessible name.
    <div
      className={`qf-chart ${className}`.trim()}
      style={{
        width,
        ...(height == null ? { aspectRatio: `${QF_CHART_ASPECT_RATIO} / 1` } : { height }),
        ...style,
      }}
      role={interactive ? 'button' : 'img'}
      aria-label={ariaLabel}
      aria-describedby={ariaDescribedBy}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={interactive ? onKeyDown : undefined}
      data-chart-engine="qf-charts"
      data-chart-lifecycle="qf-chart"
    >
      <div ref={hostRef} className="qf-chart-canvas" aria-hidden="true" />
      {error ? (
        <div className="qf-chart-error" role="alert">
          <span>Chart failed to update</span>
          <button type="button" onClick={retry}>
            Retry
          </button>
        </div>
      ) : null}
    </div>
  );
}
