/**
 * Immediate cursor tracking for tall tooltips in scrolling chart workspaces.
 * USAGE: const behavior = useMemo(createViewportTooltip, []); tooltip: { ...behavior }.
 */

// --------------------------------------------------------------------------- #
// Contracts
// --------------------------------------------------------------------------- #

export interface ViewportTooltipSize {
  contentSize: readonly number[];
  viewSize: readonly number[];
}

export interface ViewportTooltipBehavior {
  appendTo: (chart: HTMLElement) => HTMLElement;
  confine: false;
  transitionDuration: 0;
  hideDelay: 0;
  position: (
    point: readonly number[],
    params: unknown,
    element: unknown,
    rect: unknown,
    size: ViewportTooltipSize,
  ) => [number, number];
}

// --------------------------------------------------------------------------- #
// Positioning
// --------------------------------------------------------------------------- #

const INSET = 12;
const GAP = 14;

/** Keep the returned object stable: ECharts calls appendTo only at initialization. */
export function createViewportTooltip(): ViewportTooltipBehavior {
  let chart: HTMLElement | undefined;
  const scrollParents: { element: HTMLElement; x: boolean; y: boolean }[] = [];
  return {
    appendTo: (host) => {
      chart = host;
      scrollParents.length = 0;
      for (let parent = host.parentElement; parent; parent = parent.parentElement) {
        const style = getComputedStyle(parent);
        const x = /auto|scroll|overlay/.test(style.overflowX);
        const y = /auto|scroll|overlay/.test(style.overflowY);
        if (x || y) scrollParents.push({ element: parent, x, y });
      }
      return host.ownerDocument.body;
    },
    confine: false,
    // Nonzero duration also makes ECharts throttle position updates to 50ms.
    transitionDuration: 0,
    hideDelay: 0,
    position: (point, _params, _element, _rect, size) => {
      if (!chart) return [point[0] ?? 0, point[1] ?? 0];
      const origin = chart.getBoundingClientRect();
      let left = 0;
      let top = 0;
      let right = window.innerWidth;
      let bottom = window.innerHeight;
      for (const parent of scrollParents) {
        const scrollX = parent.x && parent.element.scrollWidth > parent.element.clientWidth;
        const scrollY = parent.y && parent.element.scrollHeight > parent.element.clientHeight;
        if (!scrollX && !scrollY) continue;
        const bounds = parent.element.getBoundingClientRect();
        if (scrollX) {
          left = Math.max(left, bounds.left);
          right = Math.min(right, bounds.right);
        }
        if (scrollY) {
          top = Math.max(top, bounds.top);
          bottom = Math.min(bottom, bounds.bottom);
        }
      }
      // Clamp continuously at an edge instead of flipping a full box width or
      // height across the cursor. Coordinates returned to ECharts remain local.
      return [
        Math.max(
          left + INSET,
          Math.min(origin.left + (point[0] ?? 0) + GAP, right - (size.contentSize[0] ?? 0) - INSET),
        ) - origin.left,
        Math.max(
          top + INSET,
          Math.min(origin.top + (point[1] ?? 0) + GAP, bottom - (size.contentSize[1] ?? 0) - INSET),
        ) - origin.top,
      ];
    },
  };
}
