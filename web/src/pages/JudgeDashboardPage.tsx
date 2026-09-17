import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { RequireRole } from '../components/auth/guards';
import { EmptyState, ErrorState, SkeletonRows } from '../components/feedback';
import { Badge, Button, Card } from '../components/ui';
import { ApiError, api } from '../lib/api';
import type { Assignment, JudgeProgress } from '../types';

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

function JudgeDashboard() {
  const [progress, setProgress] = useState<JudgeProgress | null>(null);
  const [error, setError] = useState<string | null>(null);

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
        </>
      )}
    </div>
  );
}
