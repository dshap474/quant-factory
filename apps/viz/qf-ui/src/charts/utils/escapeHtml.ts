/**
 * Escape untrusted text before interpolating it into ECharts HTML tooltips.
 *
 * USAGE:
 *   escapeHtml('<label>');
 */

// --------------------------------------------------------------------------- #
// Escaping
// --------------------------------------------------------------------------- #

export function escapeHtml(value: string): string {
  return value.replace(
    /[&<>'"]/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character] ??
      character,
  );
}
