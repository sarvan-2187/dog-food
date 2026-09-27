import { useCallback, useEffect, useState } from 'react';
import { ApiError, api } from '../lib/api';
import { Button, Card } from '../components/ui';
import { ErrorState, SkeletonRows } from '../components/feedback';

interface FlaggedVote {
  vote_id: number;
  submission_id: number;
  submission_title: string;
  voter: string;
  created_at: string;
  voters_on_client: number;
}

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

/**
 * Votes cast from one client (IP + browser) by several different voters.
 * A signal, not a verdict - a shared lab machine looks the same - so the
 * organizer decides, and every void is written to the audit log.
 * Hidden entirely while there is nothing to review.
 */
export function SuspiciousVotesCard({
  eventId,
  onToast,
}: {
  eventId: number;
  onToast: (message: string, ok: boolean) => void;
}) {
  const [rows, setRows] = useState<FlaggedVote[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const load = useCallback(() => {
    setError(null);
    api
      .get<FlaggedVote[]>(`/api/events/${eventId}/votes/flagged`)
      .then(setRows)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load flagged votes.'));
  }, [eventId]);

  useEffect(load, [load]);

  async function voidVote(row: FlaggedVote) {
    if (!window.confirm(`Void this vote for "${row.submission_title}"? It is removed from the count and logged.`)) return;
    setBusy(row.vote_id);
    try {
      await api.del(`/api/events/${eventId}/votes/${row.vote_id}`);
      onToast('Vote voided and recorded in the audit log.', true);
      load();
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Could not void that vote.', false);
    } finally {
      setBusy(null);
    }
  }

  if (!error && rows?.length === 0) return null;

  return (
    <Card
      title="Suspicious votes"
      meta={rows ? `${rows.length} to review` : undefined}
      footer="Several voters used the same device and network. That can be a shared lab machine, so check before voiding."
    >
      {error && <ErrorState description={error} onRetry={load} />}
      {!rows && !error && <SkeletonRows rows={2} cols={2} />}
      {rows && rows.length > 0 && (
        <ul className="flex flex-col divide-y divide-border-subtle" aria-label="Flagged votes">
          {rows.map((r) => (
            <li key={r.vote_id} className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
              <span className="min-w-0">
                <span className="block text-body text-ink-800">{r.submission_title}</span>
                <span className="block text-meta text-ink-500">
                  {r.voter} · {when(r.created_at)} · {r.voters_on_client} voters on this device
                </span>
              </span>
              <Button
                variant="secondary"
                size="sm"
                loading={busy === r.vote_id}
                loadingLabel="Voiding..."
                onClick={() => voidVote(r)}
              >
                Void
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
