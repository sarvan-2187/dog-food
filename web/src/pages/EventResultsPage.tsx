import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { EligibilityCard } from '../components/EligibilityCard';
import { SuspiciousVotesCard } from '../components/SuspiciousVotesCard';
import { JudgeInvitePanel } from '../components/JudgeInvitePanel';
import { JudgePanelCard } from '../components/JudgePanelCard';
import { WinnersEditor } from '../components/EventSections';
import { RequireRole } from '../components/auth/guards';
import { EmptyState, ErrorState, SkeletonRows, Toast, ToastRegion } from '../components/feedback';
import { Badge, Button, Card } from '../components/ui';
import { ApiError, api } from '../lib/api';
import { Input, SimpleSelect } from '../components/ui';
import type { AssignmentSummary, EventRecord, ResultRow } from '../types';

const VOTING_ACCESS: { value: EventRecord['voting_access']; label: string }[] = [
  { value: 'authenticated', label: 'Signed-in accounts' },
  { value: 'email', label: 'Anyone who confirms an email' },
  { value: 'open', label: 'Anyone with the link' },
];

const EXPORTS = [
  { file: 'users', label: 'Users' },
  { file: 'submissions', label: 'Submissions' },
  { file: 'assignments', label: 'Assignments' },
  { file: 'scores', label: 'Raw scores' },
  { file: 'results', label: 'Normalised results' },
] as const;

// Radix Select can't hold an empty value, so "every track" gets a sentinel.
const ALL_TRACKS = '__all__';

/** An ISO instant as the value a datetime-local input expects, in local time. */
function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

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
  // Track standings for track prizes: the same normalised ranking, narrowed.
  const [trackFilter, setTrackFilter] = useState(ALL_TRACKS);
  const [error, setError] = useState<string | null>(null);
  const [assigning, setAssigning] = useState(false);
  const [summary, setSummary] = useState<AssignmentSummary | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [savingVoting, setSavingVoting] = useState(false);
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

  async function updateVoting(patch: {
    voting_enabled?: boolean;
    voting_access?: EventRecord['voting_access'];
    results_hidden_until?: string | null;
    voting_requires_verified?: boolean;
    voting_account_cutoff?: string | null;
  }, message?: string) {
    if (!event) return;
    setSavingVoting(true);
    try {
      const updated = await api.patch<EventRecord>(`/api/events/${event.id}`, patch);
      setEvent(updated);
      setToast({
        message: message ??
          (patch.voting_access !== undefined
            ? 'Who can vote was updated.'
            : patch.voting_enabled === undefined
            ? 'Results reveal time updated.'
            : patch.voting_enabled
              ? 'Community voting is now open.'
              : 'Community voting is now closed.'),
        ok: true,
      });
    } catch (err) {
      setToast({ message: err instanceof ApiError ? err.message : 'Could not update voting.', ok: false });
    } finally {
      setSavingVoting(false);
    }
  }

  async function saveDeadline(judging_deadline: string | null) {
    if (!event) return;
    try {
      setEvent(await api.patch<EventRecord>(`/api/events/${event.id}`, { judging_deadline }));
      setToast({ message: judging_deadline ? 'Judging deadline saved.' : 'Judging deadline removed.', ok: true });
    } catch (err) {
      setToast({ message: err instanceof ApiError ? err.message : 'Could not save the deadline.', ok: false });
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

  const trackOptions = [...new Set((rows ?? []).map((r) => r.track).filter(Boolean))].sort();
  const shown = (rows ?? []).filter((r) => trackFilter === ALL_TRACKS || r.track === trackFilter);
  const place = (r: ResultRow) => (trackFilter === ALL_TRACKS ? r.rank : r.track_rank ?? r.rank);

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
        meta={<Link to={`/events/${slug}/rubric`} className="text-meta text-brand-500">Edit rubrics</Link>}
      >
        <div className="flex flex-col gap-4">
          <p className="text-body text-ink-600">
            Assignment gives each submitted entry three judges, never one from the submitting team. Running it again
            only fills gaps - it never duplicates existing assignments.
          </p>
          <div className="flex flex-wrap items-end gap-3">
            <Button variant="primary" loading={assigning} loadingLabel="Assigning judges..." onClick={runAssignment}>
              Assign judges
            </Button>
            <Input
              label="Judges should finish by"
              type="datetime-local"
              className="md:w-64"
              value={event?.judging_deadline ? toLocalInput(event.judging_deadline) : ''}
              onChange={(e) => saveDeadline(e.target.value ? new Date(e.target.value).toISOString() : null)}
              hint="Shown to judges; late scores still count. Leave empty for none."
            />
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

      <Card title="Community voting" meta={event?.voting_enabled ? 'Open' : 'Closed'}>
        <div className="flex flex-col gap-4">
          <p className="text-body text-ink-600">
            {event?.voting_enabled
              ? `${VOTING_ACCESS.find((o) => o.value === event.voting_access)?.label ?? 'Signed-in accounts'} can vote; anyone signed in can comment.`
              : 'Voting is closed. Turn it on to let the community vote on submissions in the gallery.'}
          </p>
          <div className="flex flex-wrap items-end gap-3">
            <Button
              variant={event?.voting_enabled ? 'secondary' : 'primary'}
              loading={savingVoting}
              loadingLabel="Saving..."
              onClick={() => updateVoting({ voting_enabled: !event?.voting_enabled })}
            >
              {event?.voting_enabled ? 'Close voting' : 'Open voting'}
            </Button>
            <SimpleSelect
              label="Who can vote"
              value={event?.voting_access ?? 'authenticated'}
              onChange={(value) => updateVoting({ voting_access: value as EventRecord['voting_access'] })}
              options={VOTING_ACCESS}
              triggerClassName="md:w-64"
              disabled={savingVoting}
            />
            <Input
              label="Hide vote counts until"
              type="datetime-local"
              className="md:w-64"
              value={event?.results_hidden_until ? toLocalInput(event.results_hidden_until) : ''}
              onChange={(e) =>
                updateVoting({
                  results_hidden_until: e.target.value ? new Date(e.target.value).toISOString() : null,
                })
              }
              hint="Leave empty to show counts immediately."
            />
          </div>
          <fieldset className="flex flex-col gap-3 border-t border-border-subtle pt-4">
            <legend className="text-label text-ink-800">Stop one person voting from several accounts</legend>
            <label className="flex items-start gap-2 text-body text-ink-700">
              <input
                type="checkbox"
                className="mt-1"
                checked={Boolean(event?.voting_requires_verified)}
                disabled={savingVoting}
                onChange={(e) =>
                  updateVoting(
                    { voting_requires_verified: e.target.checked },
                    e.target.checked ? 'Only verified emails can vote now.' : 'Email verification is no longer required.',
                  )
                }
              />
              <span>
                Require a verified email to vote
                <span className="block text-meta text-ink-500">Needs email set up. Each extra account then needs an inbox of its own.</span>
              </span>
            </label>
            <Input
              label="Only accounts created before"
              type="datetime-local"
              className="md:w-64"
              value={event?.voting_account_cutoff ? toLocalInput(event.voting_account_cutoff) : ''}
              onChange={(e) =>
                updateVoting(
                  { voting_account_cutoff: e.target.value ? new Date(e.target.value).toISOString() : null },
                  'Voter cutoff updated.',
                )
              }
              hint="Accounts made after this can't vote, so new accounts can't be spun up to swing a result. Works offline."
            />
          </fieldset>
        </div>
      </Card>

      {/* Both are per-event since Phase 10.1, so they wait for the event to load
          rather than rendering against an id that isn't known yet. */}
      {event && (
        <>
          <SuspiciousVotesCard eventId={event.id} onToast={(message, ok) => setToast({ message, ok })} />
          <EligibilityCard eventId={event.id} onToast={(message, ok) => setToast({ message, ok })} onChanged={load} />
          <JudgePanelCard eventId={event.id} tracks={event.tracks} onToast={(message, ok) => setToast({ message, ok })} />
          <JudgeInvitePanel eventId={event.id} onToast={(message, ok) => setToast({ message, ok })} />
          <WinnersEditor eventId={event.id} onToast={(message, ok) => setToast({ message, ok })} />
        </>
      )}

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
        <Card title="Normalised standings" meta={`${shown.length} submissions`}>
          <p className="mb-4 text-meta text-ink-500">
            Ranking uses the normalised score, which cancels out how harsh or generous each individual judge is. The
            raw mean is shown alongside so you can see where the two disagree.
          </p>
          {trackOptions.length > 0 && (
            <SimpleSelect
              label="Standings for"
              className="mb-4 sm:w-72"
              value={trackFilter}
              onChange={setTrackFilter}
              options={[
                { value: ALL_TRACKS, label: 'All tracks (overall)' },
                ...trackOptions.map((t) => ({ value: t, label: t })),
              ]}
              hint={
                trackFilter === ALL_TRACKS
                  ? undefined
                  : 'Places within this track, on the same normalised scores: every judge is calibrated on everything they scored.'
              }
            />
          )}

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
                {shown.map((r) => (
                  <tr key={r.submission_id} className="border-b border-border-subtle last:border-b-0">
                    <td className="tabular py-3 pr-3 text-ink-500">{place(r)}</td>
                    <th scope="row" className="py-3 pr-3 text-left font-normal text-ink-800">
                      {r.submission_title}
                      {r.track && <span className="block text-meta text-ink-500">{r.track}</span>}
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
            {shown.map((r) => (
              <li key={r.submission_id} className="rounded-md border border-border-subtle p-card-sm">
                <div className="mb-2 flex items-baseline justify-between gap-2">
                  <span className="text-label text-ink-800">
                    #{place(r)} {r.submission_title}
                  </span>
                  <Badge status="info">{r.display.toFixed(1)}</Badge>
                </div>
                <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-meta text-ink-600">
                  <dt>Team</dt>
                  <dd className="text-right text-ink-800">{r.team_name}</dd>
                  {r.track && (
                    <>
                      <dt>Track</dt>
                      <dd className="text-right text-ink-800">{r.track}</dd>
                    </>
                  )}
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
