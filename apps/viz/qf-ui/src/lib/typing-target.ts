/**
 * Whether a keyboard event comes from editable text, so global shortcuts (⌘K,
 * arrow paging, `[` / `]`) stand aside while the user types.
 *
 * USAGE:
 *   window.addEventListener('keydown', (event) => {
 *     if (isTypingTarget(event.target)) return;
 *     …
 *   });
 */

// --------------------------------------------------------------------------- #
// Predicate
// --------------------------------------------------------------------------- #

/** True for inputs, textareas, selects and contenteditable regions (or anything inside them). */
export function isTypingTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || target.closest('input, textarea, select') !== null)
  );
}
