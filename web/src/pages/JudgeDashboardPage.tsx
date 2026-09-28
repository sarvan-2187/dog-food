import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { RequireRole } from '../components/auth/guards';
import { EmptyState, ErrorState, SkeletonRows, Toast, ToastRegion } from '../components/feedback';
import { Badge, Button, Card } from '../components/ui';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import type { Assignment, JudgeEvent, JudgeProgress } from '../types';

export function JudgeDashboardPage() {
  return (
    <RequireRole roles={['judge']}>
      <JudgeDashboard />
    </RequireRole>
  );
}

/** PLAN.md 4.4: the numbers that matter lead, above the fold, not buried in a table. */
function ProgressHeadline({ completed, total }: { completed: number; total: number }) {
  const pct = total === 0 ? 0 : Math.round((completed / total) * 100);
  const done = total > 0 && completed === total;
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface-0 p-card">
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="tabular text-display text-ink-900">
          {completed} of {total}
        </span>
        <span className="text-body-lg text-ink-600">assignments completed</span>
        {done && <Badge status="success"><span aria-hidden="true">&#10003;</span> All done</Badge>}
      </div>
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-surface-200"
        role="progressbar"
        aria-valuenow={completed}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-label={`${completed} of ${total} assignments completed`}
      >
        <div
          className={done ? 'h-full bg-success-fg' : 'h-full bg-brand-500'}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-meta text-ink-500">
        {done
          ? 'Every submission assigned to you has been scored. You can still revise any score.'
          : `${total - completed} still to score.`}
      </p>
    </div>
  );
}

function AssignmentRow({ assignment }: { assignment: Assignment }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle py-3 last:border-b-0">
      <div className="flex min-w-0 flex-col">
        <span className="truncate text-label text-ink-800">{assignment.submission_title}</span>
        <span className="text-meta text-ink-500">Submission #{assignment.submission_id}</span>
      </div>
      <div className="flex items-center gap-3">
        {/* Colour is never the only signal (PLAN.md 4.5): each badge carries text. */}
        {assignment.scored ? (
          <Badge status="success"><span aria-hidden="true">&#10003;</span> Scored</Badge>
        ) : (
          <Badge status="warning">Not scored</Badge>
        )}
        <Link to={`/assignments/${assignment.id}/score`}>
          <Button variant={assignment.scored ? 'secondary' : 'primary'} size="sm">
            {assignment.scored ? 'Review score' : 'Score now'}
          </Button>
        </Link>
      </div>
    </li>
  );
}

/**
 * Signed participation records (PLAN.md Phase 4 T4): proof a judge did the
 * work, verifiable against the published key without trusting this server
 * again. One per event, because that is what the record is scoped to.
 *
 * The server refuses a record for an event with no assignments, so the list is
 * built from the judge's own assignments - there is never a button here that
 * is going to 404.
 */
function ParticipationRecords({
  assignments,
  judgeId,
  onToast,
}: {
  assignments: Assignment[];
  judgeId: number;
  onToast: (message: string, ok: boolean) => void;
}) {
  const [busy, setBusy] = useState<number | null>(null);

  const events = Array.from(
    new Map(assignments.map((a) => [a.event_id, a.event_name])).entries(),
  ).map(([id, name]) => ({ id, name }));

  async function download(eventId: number, eventName: string) {
    setBusy(eventId);
    try {
      await api.download(
        `/api/events/${eventId}/judges/${judgeId}/participation-record`,
        `participation-record-event-${eventId}.json`,
      );
      onToast(`Signed record for ${eventName} downloaded.`, true);
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Could not download your record. Please try again.', false);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card title="Participation record" meta="Signed">
      <div className="flex flex-col gap-4">
        <p className="text-body text-ink-600">
          A signed statement of how much judging you did on an event - assigned and scored counts, and when it was
          issued. Anyone can check it against HackFlow's published key at{' '}
          <a className="text-brand-500" href="/api/public-key">
            /api/public-key
          </a>{' '}
          without having to take this server's word for it a second time.
        </p>
        <div className="flex flex-wrap gap-2">
          {events.map((e) => (
            <Button
              key={e.id}
              variant="secondary"
              size="sm"
              loading={busy === e.id}
              loadingLabel="Signing..."
              disabled={busy !== null && busy !== e.id}
              onClick={() => download(e.id, e.name)}
            >
              {e.name || `Event #${e.id}`}
            </Button>
          ))}
        </div>
      </div>
    </Card>
  );
}

/**
 * PLAN.md 10.3: judging opens only once an event's submissions close, so a
 * judge on an event that's still running sees when that will be, rather than
 * an empty list and no explanation.
 */
function JudgingEvents() {
  const [events, setEvents] = useState<JudgeEvent[] | null>(null);

  useEffect(() => {
    api
      .get<JudgeEvent[]>('/api/judge/events')
      .then(setEvents)
      .catch(() => setEvents([]));
  }, []);

  const waiting = (events ?? []).filter((e) => !e.judging_open);
  if (waiting.length === 0) return null;
  return (
    <Card title="Coming up" meta={`${waiting.length} event${waiting.length === 1 ? '' : 's'}`}>
      <ul className="flex flex-col divide-y divide-border-subtle">
        {waiting.map((e) => (
          <li key={e.event_id} className="flex flex-wrap items-baseline justify-between gap-2 py-3 first:pt-0 last:pb-0">
            <Link to={`/events/${e.slug}`} className="text-label text-ink-800 hover:text-brand-500">
              {e.name}
            </Link>
            <span className="text-meta text-ink-500">
              Judging opens {new Date(e.end_at).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function JudgeDashboard() {
  const { user } = useAuth();
  const [progress, setProgress] = useState<JudgeProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);

  const load = useCallback(() => {
    setError(null);
    setProgress(null);
    api
      .get<JudgeProgress>('/api/judge/assignments')
      .then(setProgress)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load your assignments.'));
  }, []);

  useEffect(load, [load]);

  return (
    <div className="mx-auto flex max-w-[1200px] flex-col gap-6 px-4 py-section md:px-6">
      <h1 className="text-h1 text-ink-900">Judging</h1>

      <JudgingEvents />

      {progress === null && !error && <SkeletonRows rows={4} cols={2} />}
      {error && <ErrorState description={error} onRetry={load} />}

      {progress && progress.total === 0 && (
        <EmptyState
          title="No submissions assigned to you yet"
          description="Judging assignments are made by the organizer once submissions close. Nothing is missing on your side - this page will fill in as soon as they run the assignment."
        />
      )}

      {progress && progress.total > 0 && (
        <>
          <ProgressHeadline completed={progress.completed} total={progress.total} />

          {progress.pending.length > 0 && (
            <Card title="Still to score" meta={`${progress.pending.length} pending`}>
              <ul className="flex flex-col">
                {progress.pending.map((a) => (
                  <AssignmentRow key={a.id} assignment={a} />
                ))}
              </ul>
            </Card>
          )}

          {progress.done.length > 0 && (
            <Card title="Scored" meta={`${progress.done.length} done`}>
              <ul className="flex flex-col">
                {progress.done.map((a) => (
                  <AssignmentRow key={a.id} assignment={a} />
                ))}
              </ul>
            </Card>
          )}

          {user && (
            <ParticipationRecords
              assignments={[...progress.pending, ...progress.done]}
              judgeId={user.id}
              onToast={(message, ok) => setToast({ message, ok })}
            />
          )}
        </>
      )}

      <ToastRegion>
        {toast && (
          <Toast status={toast.ok ? 'success' : 'danger'} message={toast.message} onDismiss={() => setToast(null)} />
        )}
      </ToastRegion>
    </div>
  );
}
