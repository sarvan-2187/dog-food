import { useCallback, useEffect, useState } from 'react';
import { ApiError, api } from '../lib/api';
import type { PanelJudge } from '../types';
import { Button, Card } from '../components/ui';
import { EmptyState, ErrorState, SkeletonRows } from '../components/feedback';

/**
 * This event's judging panel (Phase 10.1).
 *
 * Assignment draws from this list, not from every judge account on the platform,
 * so the organizer needs to be able to see and correct it. Removing someone here
 * takes them out of future assignment runs and deliberately leaves the scores
 * they have already given alone: deleting those would silently rewrite the
 * standings.
 *
 * There is no "add by email" field on purpose. Adding requires an account that
 * already holds the judge role, and the only way to get that role is an
 * invitation — so the invite panel below is the one door in, and this card
 * cannot become a second one.
 */
export function JudgePanelCard({
  eventId,
  onToast,
}: {
  eventId: number;
  onToast: (message: string, ok: boolean) => void;
}) {
  const [judges, setJudges] = useState<PanelJudge[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<number | null>(null);

  const load = useCallback(() => {
    setError(null);
    api
      .get<PanelJudge[]>(`/api/events/${eventId}/judges`)
      .then(setJudges)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load this event’s judges.'));
  }, [eventId]);

  useEffect(load, [load]);

  async function remove(judge: PanelJudge) {
    setRemoving(judge.judge_id);
    try {
      await api.del(`/api/events/${eventId}/judges/${judge.judge_id}`);
      onToast(`${judge.name} is no longer on this event’s panel.`, true);
      load();
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Could not remove that judge.', false);
    } finally {
      setRemoving(null);
    }
  }

  return (
    <Card
      title="Judging panel"
      meta={judges ? `${judges.length} judge${judges.length === 1 ? '' : 's'}` : undefined}
      footer="Only these judges are considered when assignment runs for this event."
    >
      {error && <ErrorState description={error} onRetry={load} />}
      {!judges && !error && <SkeletonRows rows={3} cols={2} />}
      {judges?.length === 0 && (
        <EmptyState
          title="No judges yet"
          description="Invite a judge below. Accepting the invitation puts them on this event’s panel."
        />
      )}
      {judges && judges.length > 0 && (
        <ul className="flex flex-col divide-y divide-border-subtle">
          {judges.map((j) => (
            <li key={j.judge_id} className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
              <span>
                <span className="block text-body text-ink-800">{j.name}</span>
                <span className="block text-meta text-ink-500">{j.email}</span>
              </span>
              <Button
                variant="secondary"
                onClick={() => remove(j)}
                loading={removing === j.judge_id}
                loadingLabel="Removing..."
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
