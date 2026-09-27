import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ResultsHiddenNotice } from '../components/ResultsHiddenNotice';
import { VoteButton } from '../components/VoteButton';
import { EmptyState, ErrorState, SkeletonRows, Toast, ToastRegion } from '../components/feedback';
import { Badge, Button, Card } from '../components/ui';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import type { CommentRecord, EventRecord, GalleryItem, VoteResult } from '../types';

/** A comment still in flight, rendered optimistically with a pending marker. */
interface PendingComment extends CommentRecord {
  pending?: true;
}

export function SubmissionDetailPage() {
  const { submissionId = '' } = useParams();
  const { user } = useAuth();
  const [item, setItem] = useState<GalleryItem | null>(null);
  const [event, setEvent] = useState<EventRecord | null>(null);
  const [comments, setComments] = useState<PendingComment[] | null>(null);
  const [body, setBody] = useState('');
  const [touched, setTouched] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const submission = await api.get<GalleryItem>(`/api/submissions/${submissionId}`);
      setItem(submission);
      const [ev, list] = await Promise.all([
        api.get<EventRecord>(`/api/events/id/${submission.event_id}`).catch(() => null),
        api.get<CommentRecord[]>(`/api/submissions/${submissionId}/comments`).catch(() => []),
      ]);
      setEvent(ev);
      setComments(list);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load this submission.');
    }
  }, [submissionId]);

  useEffect(() => {
    load();
  }, [load]);

  const bodyError =
    touched && body.trim().length > 0 && body.trim().length < 2
      ? 'A comment must be at least 2 characters.'
      : touched && body.length > 1000
        ? 'A comment must be 1000 characters or fewer.'
        : undefined;
  const canSend = body.trim().length >= 2 && body.length <= 1000;

  async function submitComment(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!canSend || sending) return;

    // Optimistic append with a visible pending state, rolled back if the server
    // refuses (PLAN.md Phase 3 UX).
    const draft = body;
    const optimisticId = -Date.now();
    const optimistic: PendingComment = {
      id: optimisticId,
      submission_id: Number(submissionId),
      author_name: user?.name ?? 'You',
      body: draft,
      created_at: new Date().toISOString(),
      pending: true,
    };
    setComments((c) => [...(c ?? []), optimistic]);
    setBody('');
    setTouched(false);
    setSending(true);

    try {
      const saved = await api.post<CommentRecord>(`/api/submissions/${submissionId}/comments`, { body: draft });
      setComments((c) => (c ?? []).map((x) => (x.id === optimisticId ? saved : x)));
      setItem((i) => (i ? { ...i, comment_count: i.comment_count + 1 } : i));
    } catch (err) {
      setComments((c) => (c ?? []).filter((x) => x.id !== optimisticId));
      // Never lose what they typed on a failure (PLAN.md 4.3).
      setBody(draft);
      setToast({ message: err instanceof ApiError ? err.message : 'Your comment could not be posted.', ok: false });
    } finally {
      setSending(false);
    }
  }

  async function removeComment(id: number) {
    const snapshot = comments ?? [];
    setComments(snapshot.filter((c) => c.id !== id));
    try {
      await api.del(`/api/comments/${id}`);
      setItem((i) => (i ? { ...i, comment_count: Math.max(0, i.comment_count - 1) } : i));
      setToast({ message: 'Comment deleted.', ok: true });
    } catch (err) {
      setComments(snapshot);
      setToast({ message: err instanceof ApiError ? err.message : 'Could not delete that comment.', ok: false });
    }
  }

  function applyVote(result: VoteResult) {
    setItem((i) => (i ? { ...i, voted_by_me: result.voted, votes: result.votes } : i));
  }

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-section">
        <ErrorState description={error} onRetry={load} />
        <p className="mt-4 text-center text-meta">
          <Link to="/gallery" className="text-brand-500">
            Back to the gallery
          </Link>
        </p>
      </div>
    );
  }

  if (!item) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-section">
        <SkeletonRows rows={6} cols={1} />
      </div>
    );
  }

  const canModerate = user?.role === 'organizer' || user?.role === 'admin';

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-section">
      <p className="text-meta">
        <Link to="/gallery" className="text-brand-500">
          &larr; Gallery
        </Link>
      </p>

      <Card title={item.title} meta={item.track || undefined}>
        <p className="whitespace-pre-wrap text-body text-ink-700">{item.description}</p>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          {user ? (
            <VoteButton
              submissionId={item.id}
              voted={item.voted_by_me}
              votes={item.votes}
              votingEnabled={event?.voting_enabled ?? false}
              onChange={applyVote}
              onError={(message) => setToast({ message, ok: false })}
            />
          ) : (
            event?.voting_enabled && (
              <Link to={`/login?next=/submissions/${item.id}`}>
                <Button variant="secondary" size="sm">
                  Log in to vote
                </Button>
              </Link>
            )
          )}
          {item.votes === null && event?.voting_enabled && (
            <Badge status="info">Counts hidden until voting closes</Badge>
          )}
        </div>
      </Card>

      {event && <ResultsHiddenNotice hiddenUntil={event.results_hidden_until} />}

      <Card title="Comments" meta={comments ? `${comments.length}` : undefined}>
        {comments === null && <SkeletonRows rows={3} cols={1} />}

        {comments && comments.length === 0 && (
          <EmptyState
            title="No comments yet"
            description={
              user
                ? 'Be the first to say something useful about this project.'
                : 'Log in to leave the first comment.'
            }
          />
        )}

        {comments && comments.length > 0 && (
          <ul className="flex flex-col gap-4">
            {comments.map((c) => (
              <li key={c.id} className="border-b border-border-subtle pb-4 last:border-b-0 last:pb-0">
                <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-label text-ink-800">{c.author_name}</span>
                  <span className="flex items-center gap-2 text-meta text-ink-500">
                    {c.pending ? (
                      <Badge status="warning">Sending...</Badge>
                    ) : (
                      new Date(c.created_at).toLocaleString()
                    )}
                    {!c.pending && (canModerate || c.author_name === user?.name) && (
                      <Button variant="ghost" size="sm" onClick={() => removeComment(c.id)}>
                        Delete
                      </Button>
                    )}
                  </span>
                </div>
                <p className={c.pending ? 'whitespace-pre-wrap text-body text-ink-500' : 'whitespace-pre-wrap text-body text-ink-700'}>
                  {c.body}
                </p>
              </li>
            ))}
          </ul>
        )}

        {user && (
          <form className="mt-6 flex flex-col gap-2" onSubmit={submitComment} noValidate>
            <label htmlFor="comment-body" className="text-label text-ink-800">
              Add a comment
            </label>
            <textarea
              id="comment-body"
              rows={3}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              onBlur={() => setTouched(true)}
              aria-invalid={bodyError ? true : undefined}
              aria-describedby={bodyError ? 'comment-error' : 'comment-count'}
              className={[
                'rounded-md border bg-surface-0 px-3 py-2 text-body text-ink-800',
                'focus:outline-none focus:ring-[3px] focus:ring-brand-500/20',
                bodyError ? 'border-danger-fg focus:border-danger-fg' : 'border-border focus:border-brand-500',
              ].join(' ')}
            />
            <div className="flex items-center justify-between gap-3">
              {bodyError ? (
                <p id="comment-error" className="text-meta text-danger-fg">
                  {bodyError}
                </p>
              ) : (
                <p id="comment-count" className="text-meta text-ink-500">
                  {body.length}/1000
                </p>
              )}
              <Button type="submit" variant="primary" size="sm" loading={sending} loadingLabel="Posting..." disabled={!canSend}>
                Post comment
              </Button>
            </div>
          </form>
        )}
      </Card>

      <ToastRegion>
        {toast && <Toast status={toast.ok ? 'success' : 'danger'} message={toast.message} onDismiss={() => setToast(null)} />}
      </ToastRegion>
    </div>
  );
}
