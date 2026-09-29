import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { CertificateButton } from '../components/CertificateButton';
import { DeadlineCountdown } from '../components/DeadlineCountdown';
import { ErrorState, InlineStatus, SkeletonRows, Toast, ToastRegion } from '../components/feedback';
import type { SaveState } from '../components/feedback';
import { SubmissionImages } from '../components/SubmissionImages';
import { Button, Card } from '../components/ui';
import { ApiError, api } from '../lib/api';
import type { EventRecord, Submission, Team } from '../types';

const FIELD_CLASS =
  'rounded-md border border-border bg-surface-0 px-3 text-body text-ink-800 ' +
  'focus:border-brand-500 focus:outline-none focus:ring-[3px] focus:ring-brand-500/20 ' +
  'disabled:bg-surface-100 disabled:text-ink-500';

type Field = 'title' | 'tagline' | 'description' | 'track' | 'tech_tags' | 'repo_url' | 'demo_url' | 'video_url';

const MAX_TAGLINE = 140;
const MAX_ANSWER = 1000;

/** Tags are typed as one comma-separated line; the server trims and deduplicates. */
const tagsToText = (tags: string[]) => tags.join(', ');
const textToTags = (text: string) =>
  text
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);

const LINKS: { field: 'repo_url' | 'demo_url' | 'video_url'; label: string; placeholder: string; hint: string }[] = [
  { field: 'repo_url', label: 'Code repository', placeholder: 'https://github.com/you/project', hint: 'Where judges can read the code.' },
  { field: 'demo_url', label: 'Live demo', placeholder: 'https://your-project.example.com', hint: 'A running version judges can try.' },
  { field: 'video_url', label: 'Demo video', placeholder: 'https://youtu.be/...', hint: 'A short walkthrough. Linked, not embedded.' },
];

/** Mirrors the server's rule (PLAN.md 10.5) so a bad link is flagged inline, before a save. */
function linkError(value: string): string | undefined {
  const v = value.trim();
  if (!v) return undefined;
  try {
    const url = new URL(v);
    if ((url.protocol === 'https:' || url.protocol === 'http:') && url.host) return undefined;
  } catch {
    // fall through
  }
  return 'Enter a full web address starting with https://';
}

function savedFields(s: Submission): Record<Field, string> {
  return {
    title: s.title,
    tagline: s.tagline,
    description: s.description,
    track: s.track,
    tech_tags: tagsToText(s.tech_tags),
    repo_url: s.repo_url,
    demo_url: s.demo_url,
    video_url: s.video_url,
  };
}

export function SubmissionPage() {
  const { teamId = '' } = useParams();
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [event, setEvent] = useState<EventRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [tagline, setTagline] = useState('');
  const [description, setDescription] = useState('');
  const [track, setTrack] = useState('');
  const [tags, setTags] = useState('');
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [links, setLinks] = useState({ repo_url: '', demo_url: '', video_url: '' });
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);
  const [submitLoading, setSubmitLoading] = useState(false);
  const loaded = useRef(false);
  // What the server last confirmed, so a blur with no edit does not re-PATCH and
  // an edit can be reported as "Unsaved changes" the moment it diverges.
  const saved = useRef<Record<Field, string>>({
    title: '',
    tagline: '',
    description: '',
    track: '',
    tech_tags: '',
    repo_url: '',
    demo_url: '',
    video_url: '',
  });
  const savedAnswers = useRef<Record<string, string>>({});

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
        setTagline(s.tagline);
        setDescription(s.description);
        setTrack(s.track);
        setTags(tagsToText(s.tech_tags));
        setAnswers(s.answers);
        savedAnswers.current = s.answers;
        setLinks({ repo_url: s.repo_url, demo_url: s.demo_url, video_url: s.video_url });
        saved.current = savedFields(s);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          // No draft yet is the normal starting state, not an error.
          setSubmission({
            id: 0,
            team_id: Number(teamId),
            event_id: 0,
            title: '',
            tagline: '',
            description: '',
            track: '',
            tech_tags: [],
            status: 'draft',
            created_at: '',
            updated_at: '',
            image_url: null,
            images: [],
            answers: {},
            repo_url: '',
            demo_url: '',
            video_url: '',
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
  const questions = (event?.questions ?? []).filter((q) => !q.hidden);

  const saveField = useCallback(
    async (field: Field, value: string) => {
      if (!loaded.current || deadlinePassed) return;
      if (saved.current[field] === value) return; // nothing changed on this blur
      if (field.endsWith('_url') && linkError(value)) return; // shown inline; don't send what the server will refuse
      setSaveState('saving');
      try {
        const body = field === 'tech_tags' ? { tech_tags: textToTags(value) } : { [field]: value };
        const updated = await api.patch<Submission>(`/api/teams/${teamId}/submission`, body);
        setSubmission(updated);
        saved.current = savedFields(updated);
        // Show the cleaned list (trimmed, duplicates dropped) the server kept.
        if (field === 'tech_tags') setTags(tagsToText(updated.tech_tags));
        setSaveState('saved');
      } catch (err) {
        setSaveState('unsaved');
        setToast({ message: err instanceof ApiError ? err.message : 'Could not save your changes.', ok: false });
      }
    },
    [teamId, deadlinePassed],
  );

  // Answers autosave one question at a time, like every other field.
  async function saveAnswer(id: string, value: string) {
    if (!loaded.current || deadlinePassed) return;
    if ((savedAnswers.current[id] ?? '') === value) return;
    setSaveState('saving');
    try {
      const updated = await api.patch<Submission>(`/api/teams/${teamId}/submission`, { answers: { [id]: value } });
      setSubmission(updated);
      savedAnswers.current = updated.answers;
      setSaveState('saved');
    } catch (err) {
      setSaveState('unsaved');
      setToast({ message: err instanceof ApiError ? err.message : 'Could not save your answer.', ok: false });
    }
  }

  function editAnswer(id: string, value: string) {
    setAnswers((a) => ({ ...a, [id]: value }));
    setSaveState((savedAnswers.current[id] ?? '') === value ? 'saved' : 'unsaved');
  }

  function edit(field: Field, value: string) {
    if (field === 'title') setTitle(value);
    if (field === 'tagline') setTagline(value);
    if (field === 'description') setDescription(value);
    if (field === 'track') setTrack(value);
    if (field === 'tech_tags') setTags(value);
    if (field === 'repo_url' || field === 'demo_url' || field === 'video_url') setLinks((l) => ({ ...l, [field]: value }));
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

      {submission?.disqualified_at && (
        <div role="alert" className="mb-4 rounded-md border border-border bg-danger-bg px-4 py-3 text-body text-danger-fg">
          <p className="font-medium">The organizers have ruled this entry ineligible.</p>
          <p>Reason: {submission.disqualified_reason}</p>
          <p className="mt-1 text-meta">It is not in the gallery, voting or judging. Contact the organizers to appeal.</p>
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
            <span className="text-label text-ink-800">Tagline</span>
            <input
              className={`h-10 ${FIELD_CLASS}`}
              value={tagline}
              maxLength={MAX_TAGLINE}
              placeholder="One line that sells it"
              disabled={deadlinePassed}
              aria-describedby="tagline-help"
              onChange={(e) => edit('tagline', e.target.value)}
              onBlur={() => saveField('tagline', tagline.trim())}
            />
            <span id="tagline-help" className="text-meta text-ink-500">
              Optional. Shown under the project name on gallery cards. {tagline.length} of {MAX_TAGLINE} characters.
            </span>
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
          <label className="flex flex-col gap-1.5">
            <span className="text-label text-ink-800">Tech tags</span>
            <input
              className={`h-10 ${FIELD_CLASS}`}
              value={tags}
              placeholder="python, postgres, react"
              disabled={deadlinePassed}
              aria-describedby="tech-tags-help"
              onChange={(e) => edit('tech_tags', e.target.value)}
              onBlur={() => saveField('tech_tags', tags)}
            />
            <span id="tech-tags-help" className="text-meta text-ink-500">
              Optional. Separate with commas: up to 10, each up to 30 characters. Visitors can filter the gallery by
              them.
            </span>
          </label>
          {/* PLAN.md 10.5: without these a judge scores from a paragraph of text. */}
          <fieldset className="flex flex-col gap-3">
            <legend className="mb-1 text-label text-ink-800">Links for the judges</legend>
            {LINKS.map(({ field, label, placeholder, hint }) => {
              const err = linkError(links[field]);
              return (
                <label key={field} className="flex flex-col gap-1.5">
                  <span className="text-meta text-ink-700">{label}</span>
                  <input
                    type="url"
                    inputMode="url"
                    className={`h-10 ${FIELD_CLASS}`}
                    placeholder={placeholder}
                    value={links[field]}
                    disabled={deadlinePassed}
                    aria-invalid={err ? true : undefined}
                    aria-describedby={`${field}-help`}
                    onChange={(e) => edit(field, e.target.value)}
                    onBlur={() => saveField(field, links[field].trim())}
                  />
                  <span id={`${field}-help`} className={err ? 'text-meta text-danger-fg' : 'text-meta text-ink-500'}>
                    {err ?? hint}
                  </span>
                </label>
              );
            })}
          </fieldset>
          {questions.length > 0 && (
            <fieldset className="flex flex-col gap-3">
              <legend className="mb-1 text-label text-ink-800">Questions from the organizers</legend>
              {questions.map((q) => {
                const value = answers[q.id] ?? '';
                return (
                  <label key={q.id} className="flex flex-col gap-1.5">
                    <span className="text-meta text-ink-700">
                      {q.prompt}
                      {q.required && <span className="text-danger-fg"> (required to submit)</span>}
                    </span>
                    <textarea
                      rows={3}
                      maxLength={MAX_ANSWER}
                      className={`py-2 ${FIELD_CLASS}`}
                      value={value}
                      disabled={deadlinePassed}
                      onChange={(e) => editAnswer(q.id, e.target.value)}
                      onBlur={() => saveAnswer(q.id, value.trim())}
                    />
                    <span className="text-meta text-ink-500">
                      {q.public ? 'Shown on your public project page. ' : 'Only the organizers and judges see this. '}
                      {value.length} of {MAX_ANSWER} characters.
                    </span>
                  </label>
                );
              })}
            </fieldset>
          )}
          {submission.id !== 0 && !deadlinePassed && (
            <div className="flex flex-col gap-1.5">
              <span className="text-label text-ink-800">Images</span>
              <SubmissionImages
                teamId={teamId}
                images={submission.images}
                onChange={(images) =>
                  setSubmission((s) => (s ? { ...s, images, image_url: images[0]?.url ?? null } : s))
                }
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
