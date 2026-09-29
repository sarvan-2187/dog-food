import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { ApiError, api } from '../lib/api';
import type { EventJudgeRow, EventJudges } from '../types';
import { Badge, Button, Card, Input, SimpleSelect } from '../components/ui';
import { EmptyState, ErrorState, SkeletonRows } from '../components/feedback';
import { DueBadge } from './DueBadge';

// Radix Select can't hold an empty value, so "no track" gets a sentinel.
const ANY_TRACK = '__any__';

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

/**
 * This event's judging panel and how far each judge has got (PLAN.md 10.1, 10.7).
 *
 * Assignment draws from this list, not from every judge account on the
 * platform, so the organizer needs to be able to see and correct it. The card
 * leads with the one number that matters - how many scores are in - and lists
 * the judge furthest behind first, since that's who needs a nudge.
 *
 * Removing a judge releases their unscored work for re-assignment and leaves
 * the scores they already gave alone: deleting those would silently rewrite
 * the standings. "Add an existing judge" only accepts an account that already
 * holds the judge role, so it is not a second route into the role - an
 * invitation (below) remains the only one.
 *
 * A judge can be given one of the event's tracks (DOGFOOD T2). The server is
 * what enforces it: assignment, the score sheet and scoring all refuse an entry
 * outside that track, so this selector only chooses, it never hides.
 */
export function JudgePanelCard({
  eventId,
  tracks,
  onToast,
}: {
  eventId: number;
  tracks: string[];
  onToast: (message: string, ok: boolean) => void;
}) {
  const [data, setData] = useState<EventJudges | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [addError, setAddError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    api
      .get<EventJudges>(`/api/events/${eventId}/judges`)
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load this event's judges."));
  }, [eventId]);

  useEffect(load, [load]);

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setBusy('add');
    setAddError(null);
    try {
      const judge = await api.post<EventJudgeRow>(`/api/events/${eventId}/judges`, { email: email.trim() });
      onToast(`${judge.name} is now on this event's panel.`, true);
      setEmail('');
      load();
    } catch (err) {
      setAddError(err instanceof ApiError ? err.message : 'Could not add that judge.');
    } finally {
      setBusy(null);
    }
  }

  async function remove(judge: EventJudgeRow) {
    const pending = judge.assigned - judge.scored;
    const detail =
      pending > 0
        ? ` Their ${pending} unscored project${pending === 1 ? '' : 's'} will be released; press Assign judges to hand them on.`
        : '';
    if (!window.confirm(`Remove ${judge.name} from this event's panel?${detail} Scores they already gave stay.`)) return;
    setBusy(`remove-${judge.user_id}`);
    try {
      const r = await api.del<{ removed_assignments: number; kept_scores: number }>(
        `/api/events/${eventId}/judges/${judge.user_id}`,
      );
      onToast(
        `${judge.name} removed. ${r.removed_assignments} unscored project${r.removed_assignments === 1 ? '' : 's'} released.`,
        true,
      );
      load();
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Could not remove that judge.', false);
    } finally {
      setBusy(null);
    }
  }

  async function setTrack(judge: EventJudgeRow, value: string) {
    const track = value === ANY_TRACK ? null : value;
    setBusy(`track-${judge.user_id}`);
    try {
      await api.put<{ track: string | null }>(`/api/events/${eventId}/judges/${judge.user_id}/track`, { track });
      onToast(
        track
          ? `${judge.name} now judges ${track} only. Press Assign judges to rebalance unscored work.`
          : `${judge.name} can now judge any track.`,
        true,
      );
      load();
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Could not change that track.', false);
    } finally {
      setBusy(null);
    }
  }

  async function remind(judge: EventJudgeRow) {
    setBusy(`remind-${judge.user_id}`);
    try {
      const r = await api.post<{ sent_to: string; remaining: number }>(
        `/api/events/${eventId}/judges/${judge.user_id}/remind`,
      );
      onToast(`Reminder sent to ${r.sent_to} (${r.remaining} left to score).`, true);
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Could not send a reminder.', false);
    } finally {
      setBusy(null);
    }
  }

  const judges = data?.judges ?? null;
  const pct = data && data.assigned > 0 ? Math.round((data.scored / data.assigned) * 100) : 0;
  const pastDeadline = Boolean(data?.judging_deadline && new Date(data.judging_deadline).getTime() < Date.now());

  return (
    <Card
      title="Judging progress"
      meta={judges ? `${judges.length} judge${judges.length === 1 ? '' : 's'}` : undefined}
      footer="Only these judges are considered when assignment runs for this event."
    >
      <div data-tour="judging-progress" className="flex flex-col gap-5">
        {error && <ErrorState description={error} onRetry={load} />}
        {!data && !error && <SkeletonRows rows={3} cols={2} />}

        {data && data.assigned > 0 && (
          <div className="flex flex-col gap-2">
            <p className="flex flex-wrap items-baseline gap-2">
              <span className="tabular text-h2 text-ink-900">
                {data.scored} of {data.assigned}
              </span>
              <span className="text-body text-ink-600">scores in</span>
              <DueBadge at={data.judging_deadline} />
            </p>
            <div
              className="h-2 w-full overflow-hidden rounded-full bg-surface-200"
              role="progressbar"
              aria-valuenow={data.scored}
              aria-valuemin={0}
              aria-valuemax={data.assigned}
              aria-label={`${data.scored} of ${data.assigned} scores in`}
            >
              <div className={pct === 100 ? 'h-full bg-success-fg' : 'h-full bg-brand-500'} style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}

        {judges?.length === 0 && (
          <EmptyState
            title="No judges yet"
            description="Invite a judge below, or add someone who already judges on HackFlow."
          />
        )}

        {judges && judges.length > 0 && (
          <ul className="flex flex-col divide-y divide-border-subtle" aria-label="Judges on this event">
            {judges.map((j) => {
              const done = j.assigned > 0 && j.scored === j.assigned;
              return (
                <li key={j.user_id} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block text-body text-ink-800">{j.name}</span>
                      <span className="block truncate text-meta text-ink-500">{j.email}</span>
                    </span>
                    <span className="flex flex-wrap items-center gap-2">
                      {pastDeadline && j.assigned > j.scored && <Badge status="danger">Overdue</Badge>}
                      {j.assigned === 0 ? (
                        <Badge status="neutral">Nothing assigned</Badge>
                      ) : (
                        <Badge status={done ? 'success' : 'warning'}>
                          {j.scored} / {j.assigned} scored
                        </Badge>
                      )}
                      {data?.email_enabled && j.assigned > j.scored && (
                        <Button
                          variant="ghost"
                          size="sm"
                          loading={busy === `remind-${j.user_id}`}
                          loadingLabel="Sending..."
                          onClick={() => remind(j)}
                        >
                          Remind
                        </Button>
                      )}
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={busy === `remove-${j.user_id}`}
                        loadingLabel="Removing..."
                        onClick={() => remove(j)}
                      >
                        Remove
                      </Button>
                    </span>
                  </div>
                  {tracks.length > 0 && (
                    <SimpleSelect
                      label={`Track for ${j.name}`}
                      className="sm:w-72"
                      value={j.track ?? ANY_TRACK}
                      onChange={(v) => setTrack(j, v)}
                      disabled={busy === `track-${j.user_id}`}
                      options={[
                        { value: ANY_TRACK, label: 'Any track' },
                        ...tracks.map((t) => ({ value: t, label: t })),
                      ]}
                    />
                  )}
                  {j.last_activity && (
                    <span className="text-meta text-ink-500">Last scored {when(j.last_activity)}</span>
                  )}
                  {j.conflicts.map((c) => (
                    <p key={c.submission_id} className="rounded-md bg-surface-100 px-3 py-2 text-meta text-ink-700">
                      Declared a conflict with <span className="font-medium">{c.submission_title}</span>
                      {c.reason ? ` - "${c.reason}"` : ''}. It won't be assigned to them again.
                    </p>
                  ))}
                </li>
              );
            })}
          </ul>
        )}

        <form className="flex flex-col gap-2 sm:flex-row sm:items-start" onSubmit={add} noValidate>
          <Input
            label="Add an existing judge"
            type="email"
            className="sm:w-80"
            placeholder="judge@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            error={addError ?? undefined}
            hint={addError ? undefined : 'For someone who already judges on HackFlow. New judges need an invitation.'}
          />
          <Button type="submit" variant="secondary" className="sm:mt-7" loading={busy === 'add'} loadingLabel="Adding...">
            Add to panel
          </Button>
        </form>
      </div>
    </Card>
  );
}
