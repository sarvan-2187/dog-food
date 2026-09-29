/**
 * PLAN.md Phase 3 UX: explain *why* results are hidden and until when, rather
 * than disabling a control with no explanation.
 */
export function ResultsHiddenNotice({ hiddenUntil }: { hiddenUntil: string | null }) {
  if (!hiddenUntil) return null;
  const when = new Date(hiddenUntil);
  if (when.getTime() <= Date.now()) return null;

  return (
    <div
      role="status"
      className="flex flex-col gap-1 rounded-md border border-border bg-info-bg px-4 py-3 text-body text-info-fg"
    >
      <span className="text-label">
        <span aria-hidden="true">&#9201;</span> Vote counts are hidden until voting closes
      </span>
      <span className="text-meta">
        Results become visible on {when.toLocaleString()}. You can still vote and comment now - everyone sees the
        totals at the same time, so early counts cannot sway the vote.
      </span>
    </div>
  );
}
