import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { ErrorState, InlineStatus, SkeletonRows, Toast, ToastRegion } from '../components/feedback';
import type { SaveState } from '../components/feedback';
import { Button, Card } from '../components/ui';
import { ApiError, api } from '../lib/api';
import type { Submission } from '../types';

export function SubmissionPage() {
  const { teamId = '' } = useParams();
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [track, setTrack] = useState('');
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);
  const [submitLoading, setSubmitLoading] = useState(false);
  const loaded = useRef(false);

  useEffect(() => {
    api
      .get<Submission>(`/api/teams/${teamId}/submission`)
      .then((s) => {
        setSubmission(s);
        setTitle(s.title);
        setDescription(s.description);
        setTrack(s.track);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
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
          });
        } else {
          setError(err instanceof ApiError ? err.message : 'Could not load your submission.');
        }
      })
      .finally(() => {
        loaded.current = true;
      });
  }, [teamId]);

  async function saveField(patch: Partial<Pick<Submission, 'title' | 'description' | 'track'>>) {
    if (!loaded.current) return;
    setSaveState('saving');
    try {
      const updated = await api.patch<Submission>(`/api/teams/${teamId}/submission`, patch);
      setSubmission(updated);
      setSaveState('saved');
    } catch (err) {
      setSaveState('unsaved');
      setToast({ message: err instanceof ApiError ? err.message : 'Could not save your changes.', ok: false });
    }
  }

  async function onFinalSubmit() {
    setSubmitLoading(true);
    try {
      const updated = await api.post<Submission>(`/api/teams/${teamId}/submission/submit`);
      setSubmission(updated);
      setToast({ message: 'Submission sent for judging.', ok: true });
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
      <Card
        title="Your submission"
        meta={<InlineStatus state={saveState} />}
        footer="Fields save automatically when you click away - no manual save needed."
      >
        <div className="flex flex-col gap-4">
          {submission.status === 'submitted' && <p className="text-meta text-success-fg">Submitted - you can still edit until the deadline.</p>}
          <label className="flex flex-col gap-1.5">
            <span className="text-label text-ink-800">Title</span>
            <input
              className="h-10 rounded-md border border-border bg-surface-0 px-3 text-body text-ink-800 focus:border-brand-500 focus:outline-none focus:ring-[3px] focus:ring-brand-500/20"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onBlur={() => saveField({ title })}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-label text-ink-800">Description</span>
            <textarea
              rows={6}
              className="rounded-md border border-border bg-surface-0 px-3 py-2 text-body text-ink-800 focus:border-brand-500 focus:outline-none focus:ring-[3px] focus:ring-brand-500/20"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              onBlur={() => saveField({ description })}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-label text-ink-800">Track</span>
            <input
              className="h-10 rounded-md border border-border bg-surface-0 px-3 text-body text-ink-800 focus:border-brand-500 focus:outline-none focus:ring-[3px] focus:ring-brand-500/20"
              value={track}
              onChange={(e) => setTrack(e.target.value)}
              onBlur={() => saveField({ track })}
            />
          </label>
          <Button variant="primary" loading={submitLoading} loadingLabel="Submitting..." onClick={onFinalSubmit}>
            {submission.status === 'submitted' ? 'Re-submit' : 'Submit for judging'}
          </Button>
        </div>
      </Card>
      <ToastRegion>
        {toast && <Toast status={toast.ok ? 'success' : 'danger'} message={toast.message} onDismiss={() => setToast(null)} />}
      </ToastRegion>
    </div>
  );
}
