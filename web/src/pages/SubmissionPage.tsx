import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { CertificateButton } from '../components/CertificateButton';
import { DeadlineCountdown } from '../components/DeadlineCountdown';
import { ErrorState, InlineStatus, SkeletonRows, Toast, ToastRegion } from '../components/feedback';
import type { SaveState } from '../components/feedback';
import { ImageUpload } from '../components/ImageUpload';
import { Button, Card } from '../components/ui';
import { ApiError, api } from '../lib/api';
import type { EventRecord, Submission, Team } from '../types';

const FIELD_CLASS =
  'rounded-md border border-border bg-surface-0 px-3 text-body text-ink-800 ' +
  'focus:border-brand-500 focus:outline-none focus:ring-[3px] focus:ring-brand-500/20 ' +
  'disabled:bg-surface-100 disabled:text-ink-500';

export function SubmissionPage() {
  const { teamId = '' } = useParams();
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [event, setEvent] = useState<EventRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [track, setTrack] = useState('');
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);
  const [submitLoading, setSubmitLoading] = useState(false);
  const loaded = useRef(false);
  // What the server last confirmed, so a blur with no edit does not re-PATCH and
  // an edit can be reported as "Unsaved changes" the moment it diverges.
  const saved = useRef({ title: '', description: '', track: '' });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      // The deadline must be on screen before the participant types anything, so
      // they never discover it via a rejected save (PLAN.md 4.1). The team lookup
      // is what tells us which event this submission belongs to.
      try {
        const team = await api.get<Team>(`/api/teams/${teamId}`);
        if (!cancelled) setEvent(await api.get<EventRecord>(`/api/events/id/${team.event_id}`));
      } catch {
        // A missing deadline must not block editing; the server still enforces it.
      }

      try {
        const s = await api.get<Submission>(`/api/teams/${teamId}/submission`);
        if (cancelled) return;
        setSubmission(s);
        setTitle(s.title);
        setDescription(s.description);
        setTrack(s.track);
        saved.current = { title: s.title, description: s.description, track: s.track };
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          // No draft yet is the normal starting state, not an error.
          setSubmission({
            id: 0,
            team_id: Number(teamId),
            event_id: 0,
            title: '',
            description: '',
            track: '',
            status: 'draft',
            created_at: '',
            updated_at: '',
            image_url: null,
          });
        } else {
          setError(err instanceof ApiError ? err.message : 'Could not load your submission.');
        }
      } finally {
        if (!cancelled) loaded.current = true;
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [teamId]);

  const deadlinePassed = event ? new Date(event.end_at).getTime() <= Date.now() : false;

  const saveField = useCallback(
    async (field: 'title' | 'description' | 'track', value: string) => {
      if (!loaded.current || deadlinePassed) return;
      if (saved.current[field] === value) return; // nothing changed on this blur
      setSaveState('saving');
      try {
        const updated = await api.patch<Submission>(`/api/teams/${teamId}/submission`, { [field]: value });
        setSubmission(updated);
        saved.current = { title: updated.title, description: updated.description, track: updated.track };
        setSaveState('saved');
      } catch (err) {
        setSaveState('unsaved');
        setToast({ message: err instanceof ApiError ? err.message : 'Could not save your changes.', ok: false });
      }
    },
    [teamId, deadlinePassed],
  );

  function edit(field: 'title' | 'description' | 'track', value: string) {
    if (field === 'title') setTitle(value);
    if (field === 'description') setDescription(value);
    if (field === 'track') setTrack(value);
    setSaveState(saved.current[field] === value ? 'saved' : 'unsaved');
  }

  async function onFinalSubmit() {
    setSubmitLoading(true);
    try {
      const updated = await api.post<Submission>(`/api/teams/${teamId}/submission/submit`);
      setSubmission(updated);
      setToast({ message: 'Submission sent for judging. You can keep editing until the deadline.', ok: true });
    } catch (err) {
      setToast({ message: err instanceof ApiError ? err.message : 'Could not submit yet.', ok: false });
    } finally {
      setSubmitLoading(false);
    }
  }

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-section">
        <ErrorState description={error} />
        <p className="mt-4 text-center text-meta">
          <Link to="/teams/mine" className="text-brand-500">
            Back to my teams
          </Link>
        </p>
      </div>
    );
  }
  if (!submission) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-section">
        <SkeletonRows rows={5} cols={1} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-section">
      <p className="mb-4 text-meta">
        <Link to="/teams/mine" className="text-brand-500">
          &larr; My teams
        </Link>
      </p>

      {event && (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <DeadlineCountdown endAt={event.end_at} />
          <span className="text-meta text-ink-500">{event.name}</span>
        </div>
      )}

      {deadlinePassed && (
        <div role="alert" className="mb-4 rounded-md border border-border bg-warning-bg px-4 py-3 text-body text-warning-fg">
          The deadline has passed, so this submission can no longer be edited. What you see below is what the judges
          will review.
        </div>
      )}

      <Card
        title="Your submission"
        meta={<InlineStatus state={saveState} />}
        footer={
          deadlinePassed
            ? 'Editing is closed for this event.'
            : 'Fields save automatically when you click away - no manual save needed.'
        }
      >
        <div className="flex flex-col gap-4">
          {submission.status === 'submitted' && !deadlinePassed && (
            <p className="text-meta text-success-fg">
              <span aria-hidden="true">&#10003;</span> Submitted - you can still edit until the deadline.
            </p>
          )}
          <label className="flex flex-col gap-1.5">
            <span className="text-label text-ink-800">Title</span>
            <input
              className={`h-10 ${FIELD_CLASS}`}
              value={title}
              disabled={deadlinePassed}
              onChange={(e) => edit('title', e.target.value)}
              onBlur={() => saveField('title', title)}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-label text-ink-800">Description</span>
            <textarea
              rows={6}
              className={`py-2 ${FIELD_CLASS}`}
              value={description}
              disabled={deadlinePassed}
              onChange={(e) => edit('description', e.target.value)}
              onBlur={() => saveField('description', description)}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-label text-ink-800">Track</span>
            {event && event.tracks.length > 0 ? (
              // A dropdown commits immediately on pick - there's no natural
              // "blur" moment for a <select> the way there is for typing.
              <select
                className={`h-10 ${FIELD_CLASS}`}
                value={track}
                disabled={deadlinePassed}
                onChange={(e) => {
                  edit('track', e.target.value);
                  saveField('track', e.target.value);
                }}
              >
                <option value="">No track</option>
                {event.tracks.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            ) : (
              <input
                className={`h-10 ${FIELD_CLASS}`}
                value={track}
                disabled={deadlinePassed}
                onChange={(e) => edit('track', e.target.value)}
                onBlur={() => saveField('track', track)}
              />
            )}
          </label>
          {submission.id !== 0 && !deadlinePassed && (
            <div className="flex flex-col gap-1.5">
              <span className="text-label text-ink-800">Screenshot</span>
              <ImageUpload
                uploadUrl={`/api/teams/${teamId}/submission/image`}
                currentUrl={submission.image_url}
                label="screenshot"
                responseKey="image_url"
                onUploaded={(url) => setSubmission((s) => (s ? { ...s, image_url: url } : s))}
              />
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="primary"
              loading={submitLoading}
              loadingLabel="Submitting..."
              disabled={deadlinePassed}
              onClick={onFinalSubmit}
            >
              {submission.status === 'submitted' ? 'Re-submit' : 'Submit for judging'}
            </Button>
            {/* Only a submitted entry has a certificate to earn; the API still
                refuses one until results are revealed, and says when that is. */}
            {submission.status === 'submitted' && submission.id > 0 && (
              <CertificateButton
                submissionId={submission.id}
                onToast={(message, ok) => setToast({ message, ok })}
              />
            )}
          </div>
        </div>
      </Card>
      <ToastRegion>
        {toast && <Toast status={toast.ok ? 'success' : 'danger'} message={toast.message} onDismiss={() => setToast(null)} />}
      </ToastRegion>
    </div>
  );
}
