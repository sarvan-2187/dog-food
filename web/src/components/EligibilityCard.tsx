import { useCallback, useEffect, useState } from 'react';
import { ApiError, api } from '../lib/api';
import type { EligibilityRow } from '../types';
import { Badge, Button, Card } from '../components/ui';
import { EmptyState, ErrorState, SkeletonRows } from '../components/feedback';

/**
 * Every submitted entry, with a Disqualify / Reinstate ruling on each.
 *
 * A disqualified entry leaves the gallery, voting, judge assignment, awards and
 * standings. Scores already given are kept, so reinstating undoes it exactly.
 * The team sees the reason on their submission page, so one is required.
 */
export function EligibilityCard({
  eventId,
  onToast,
  onChanged,
}: {
  eventId: number;
  onToast: (message: string, ok: boolean) => void;
  onChanged: () => void;
}) {
  const [rows, setRows] = useState<EligibilityRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const load = useCallback(() => {
    setError(null);
    api
      .get<EligibilityRow[]>(`/api/events/${eventId}/eligibility`)
      .then(setRows)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load submissions.'));
  }, [eventId]);

  useEffect(load, [load]);

  async function rule(row: EligibilityRow, eligible: boolean) {
    let reason = '';
    if (!eligible) {
      reason =
        window.prompt(`Why is "${row.title}" ineligible? The team will see this.`)?.trim() ?? '';
      if (!reason) return;
    }
    setBusy(row.submission_id);
    try {
      await api.post(`/api/submissions/${row.submission_id}/eligibility`, { eligible, reason });
      onToast(eligible ? `${row.title} is back in the competition.` : `${row.title} was disqualified.`, true);
      load();
      onChanged();
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Could not save that ruling.', false);
    } finally {
      setBusy(null);
    }
  }

  const out = rows?.filter((r) => r.disqualified_at).length ?? 0;

  return (
    <Card
      title="Eligibility"
      meta={rows ? `${rows.length} submitted${out ? ` · ${out} disqualified` : ''}` : undefined}
      footer="Disqualified entries leave the gallery, voting, judging and standings. Scores are kept for a reinstatement."
    >
      {error && <ErrorState description={error} onRetry={load} />}
      {!rows && !error && <SkeletonRows rows={3} cols={2} />}
      {rows?.length === 0 && <EmptyState title="Nothing submitted yet" description="Entries appear here once teams submit." />}
      {rows && rows.length > 0 && (
        <ul className="flex flex-col divide-y divide-border-subtle" aria-label="Submitted entries">
          {rows.map((r) => (
            <li key={r.submission_id} className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
              <span className="min-w-0">
                <span className="block text-body text-ink-800">{r.title}</span>
                <span className="block text-meta text-ink-500">
                  {r.team_name}
                  {r.disqualified_at ? ` · ${r.disqualified_reason}` : ''}
                </span>
              </span>
              <span className="flex items-center gap-2">
                {r.disqualified_at && <Badge status="danger">Disqualified</Badge>}
                <Button
                  variant={r.disqualified_at ? 'secondary' : 'ghost'}
                  size="sm"
                  loading={busy === r.submission_id}
                  loadingLabel="Saving..."
                  onClick={() => rule(r, Boolean(r.disqualified_at))}
                >
                  {r.disqualified_at ? 'Reinstate' : 'Disqualify'}
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
