/**
 * Structure-matched fallback shown while a lazy route module loads.
 *
 * USAGE:
 *   <Suspense fallback={<WorkspaceFallback />}><Outlet /></Suspense>
 */

// --------------------------------------------------------------------------- #
// Component
// --------------------------------------------------------------------------- #

export function WorkspaceFallback() {
  return (
    <section className="workspace-fallback space-y-4" role="status" aria-label="Loading workspace">
      <div className="space-y-2">
        <div className="h-7 w-56 rounded-badge bg-secondary/70" />
        <div className="h-4 w-full max-w-xl rounded-badge bg-secondary/50" />
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {Array.from({ length: 3 }, (_, index) => (
          <div key={index} className="h-20 rounded-surface bg-secondary/40" />
        ))}
      </div>
      <div className="overflow-hidden rounded-surface bg-secondary/40">
        <div className="h-8 border-b border-border-subtle bg-secondary/40" />
        {Array.from({ length: 7 }, (_, index) => (
          <div key={index} className="h-8 border-b border-border-subtle last:border-b-0" />
        ))}
      </div>
    </section>
  );
}
