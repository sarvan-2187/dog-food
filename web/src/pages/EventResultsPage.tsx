import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { RequireRole } from '../components/auth/guards';
import { EmptyState, ErrorState, SkeletonRows, Toast, ToastRegion } from '../components/feedback';
import { Badge, Button, Card } from '../components/ui';
import { ApiError, api } from '../lib/api';
import type { AssignmentSummary, EventRecord, ResultRow } from '../types';

const EXPORTS = [
  { file: 'users', label: 'Users' },
  { file: 'submissions', label: 'Submissions' },
  { file: 'assignments', label: 'Assignments' },
  { file: 'scores', label: 'Raw scores' },
  { file: 'results', label: 'Normalised results' },
] as const;

export function EventResultsPage() {
  return (
    <RequireRole roles={['organizer', 'admin']}>
      <EventResults />
    </RequireRole>
  );
}

function EventResults() {
  const { slug = '' } = useParams();
  const [event, setEvent] = useState<EventRecord | null>(null);
  const [rows, setRows] = useState<ResultRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [assigning, setAssigning] = useState(false);
  const [summary, setSummary] = useState<AssignmentSummary | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);

  const load = useCallback(async () => {
    setError(null);
    setRows(null);
    try {
      const ev = await api.get<EventRecord>(`/api/events/${slug}`);
      setEvent(ev);
      setRows(await api.get<ResultRow[]>(`/api/events/${ev.id}/results`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load the results.');
    }
  }, [slug]);

  useEffect(() => {
    load();
  }, [load]);

  async function runAssignment() {
    if (!event) return;
    setAssigning(true);
    try {
      const result = await api.post<AssignmentSummary>(`/api/events/${event.id}/assignments`, {
        judges_per_submission: 3,
      });
      setSummary(result);
      setToast({
        message:
          result.created === 0
            ? 'Every submission already has its judges - nothing new to assign.'
            : `Assigned ${result.created} new judge-submission pairs.`,
        ok: true,
      });
      await load();
    } catch (err) {
      setToast({ message: err instanceof ApiError ? err.message : 'Could not run the assignment.', ok: false });
    } finally {
      setAssigning(false);
    }
  }

  async function download(file: string, label: string) {
    if (!event) return;
    setDownloading(file);
    try {
      await api.download(`/api/events/${event.id}/export/${file}.csv`, `event-${event.id}-${file}.csv`);
      setToast({ message: `${label} export downloaded.`, ok: true });
    } catch (err) {
      setToast({ message: err instanceof ApiError ? err.message : 'Could not export that file.', ok: false });
    } finally {
      setDownloading(null);
    }
  }

  if (error) {
    return (
      <div className="mx-auto max-w-[1200px] px-4 py-section">
        <ErrorState description={error} onRetry={load} />
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1200px] flex-col gap-6 px-4 py-section md:px-6">
      <div>
        <p className="mb-2 text-meta">
          <Link to={`/events/${slug}`} className="text-brand-500">
            &larr; {event?.name ?? 'Event'}
          </Link>
        </p>
        <h1 className="text-h1 text-ink-900">Results</h1>
      </div>

      <Card
        title="Judging"
        meta={<Link to={`/events/${slug}/rubric`} className="text-meta text-brand-500">Edit rubric</Link>}
      >
        <div className="flex flex-col gap-4">
          <p className="text-body text-ink-600">
            Assignment gives each submitted entry three judges, never one from the submitting team. Running it again
            only fills gaps - it never duplicates existing assignments.
          </p>
          <div>
            <Button variant="primary" loading={assigning} loadingLabel="Assigning judges..." onClick={runAssignment}>
              Assign judges
            </Button>
          </div>
          {summary && summary.coverage_warnings.length > 0 && (
            <div role="alert" className="rounded-md border border-border bg-warning-bg px-4 py-3 text-body text-warning-fg">
              <p className="mb-1 font-medium">Some submissions have fewer judges than requested:</p>
              <ul className="list-inside list-disc">
                {summary.coverage_warnings.map((w) => (
                  <li key={w.submission_id}>
                    {w.submission_title} - {w.judges_short} judge{w.judges_short === 1 ? '' : 's'} short
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-meta">
                Usually this means there are not enough judges who are not on the submitting team. Add more judge
                accounts and run assignment again.
              </p>
            </div>
          )}
        </div>
      </Card>

      <Card title="Exports" meta="CSV">
        <div className="flex flex-wrap gap-2">
          {EXPORTS.map((e) => (
            <Button
              key={e.file}
              variant="secondary"
              loading={downloading === e.file}
              loadingLabel="Preparing..."
              disabled={downloading !== null && downloading !== e.file}
              onClick={() => download(e.file, e.label)}
            >
              {e.label}
            </Button>
          ))}
        </div>
      </Card>

      {rows === null && <SkeletonRows rows={5} cols={5} />}

      {rows && rows.length === 0 && (
        <EmptyState
          title="No scores yet"
          description="Standings appear once judges start submitting scores. Assign judges above if you have not yet."
        />
      )}

      {rows && rows.length > 0 && (
        <Card title="Normalised standings" meta={`${rows.length} submissions`}>
          <p className="mb-4 text-meta text-ink-500">
            Ranking uses the normalised score, which cancels out how harsh or generous each individual judge is. The
            raw mean is shown alongside so you can see where the two disagree.
          </p>

          {/* Below md the table becomes stacked cards - DESIGN_SYSTEM.md 4:
              never a horizontal scrollbar on a primary view. */}
          <div className="hidden md:block">
            {/* scope="col" is not decoration: without it the browser exposes these
                as generic cells, so a screen reader reading "7.00" never says which
                column it came from (PLAN.md 4.5). */}
            <table className="w-full text-body">
              <caption className="sr-only">
                Normalised standings, ranked by normalised score, with the raw mean shown for comparison.
              </caption>
              <thead>
                <tr className="border-b border-border text-left text-meta text-ink-500">
                  <th scope="col" className="py-2 pr-3 font-medium">#</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Submission</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Team</th>
                  <th scope="col" className="py-2 pr-3 text-right font-medium">Judges</th>
                  <th scope="col" className="py-2 pr-3 text-right font-medium">Raw mean</th>
                  <th scope="col" className="py-2 pr-3 text-right font-medium">Normalised</th>
                  <th scope="col" className="py-2 text-right font-medium">Display</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.submission_id} className="border-b border-border-subtle last:border-b-0">
                    <td className="tabular py-3 pr-3 text-ink-500">{r.rank}</td>
                    <th scope="row" className="py-3 pr-3 text-left font-normal text-ink-800">
                      {r.submission_title}
                    </th>
                    <td className="py-3 pr-3 text-ink-600">{r.team_name}</td>
                    <td className="tabular py-3 pr-3 text-right text-ink-600">{r.judges}</td>
                    <td className="tabular py-3 pr-3 text-right text-ink-600">{r.raw_mean.toFixed(2)}</td>
                    <td className="tabular py-3 pr-3 text-right text-ink-800">{r.z_bar.toFixed(3)}</td>
                    <td className="tabular py-3 text-right text-ink-800">{r.display.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ul className="flex flex-col gap-3 md:hidden">
            {rows.map((r) => (
              <li key={r.submission_id} className="rounded-md border border-border-subtle p-card-sm">
                <div className="mb-2 flex items-baseline justify-between gap-2">
                  <span className="text-label text-ink-800">
                    #{r.rank} {r.submission_title}
                  </span>
                  <Badge status="info">{r.display.toFixed(1)}</Badge>
                </div>
                <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-meta text-ink-600">
                  <dt>Team</dt>
                  <dd className="text-right text-ink-800">{r.team_name}</dd>
                  <dt>Judges</dt>
                  <dd className="tabular text-right text-ink-800">{r.judges}</dd>
                  <dt>Raw mean</dt>
                  <dd className="tabular text-right text-ink-800">{r.raw_mean.toFixed(2)}</dd>
                  <dt>Normalised</dt>
                  <dd className="tabular text-right text-ink-800">{r.z_bar.toFixed(3)}</dd>
                </dl>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <ToastRegion>
        {toast && <Toast status={toast.ok ? 'success' : 'danger'} message={toast.message} onDismiss={() => setToast(null)} />}
      </ToastRegion>
    </div>
  );
}
