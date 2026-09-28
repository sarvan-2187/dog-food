import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ResultsHiddenNotice } from '../components/ResultsHiddenNotice';
import { VoteButton } from '../components/VoteButton';
import { EmptyState, ErrorState, SkeletonRows, Toast, ToastRegion } from '../components/feedback';
import { Badge, Card, Input, SimpleSelect } from '../components/ui';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import { gallerySeed } from '../lib/gallery-seed';
import type { EventRecord, GalleryItem, VoteResult } from '../types';

type Order = 'recent' | 'random' | 'votes';

const ORDERS: { value: Order; label: string }[] = [
  { value: 'recent', label: 'Most recent' },
  { value: 'random', label: 'Shuffled' },
  { value: 'votes', label: 'Most votes' },
];

export function GalleryPage() {
  const { user } = useAuth();
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [order, setOrder] = useState<Order>('recent');
  const [items, setItems] = useState<GalleryItem[] | null>(null);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);

  // One seed for the whole browser session, so a shuffled gallery does not
  // rearrange itself every time the visitor comes back (PLAN.md Phase 3 UX).
  const seed = useMemo(() => gallerySeed(), []);

  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedQ(q), 300);
    return () => window.clearTimeout(id);
  }, [q]);

  useEffect(() => {
    api.get<EventRecord[]>('/api/events').then(setEvents).catch(() => setEvents([]));
  }, []);

  useEffect(() => {
    setItems(null);
    setError(null);
    const params = new URLSearchParams({ order });
    if (debouncedQ) params.set('q', debouncedQ);
    if (order === 'random') params.set('seed', String(seed));
    api
      .get<GalleryItem[]>(`/api/gallery?${params}`)
      .then(setItems)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load the gallery.'));
  }, [debouncedQ, order, seed, retryToken]);

  const eventById = useMemo(() => new Map(events.map((e) => [e.id, e])), [events]);

  // Any event in view that is still inside its hidden window explains itself once.
  const hiddenUntil = useMemo(() => {
    const pending = events
      .filter((e) => e.results_hidden_until && new Date(e.results_hidden_until).getTime() > Date.now())
      .map((e) => e.results_hidden_until as string);
    return pending.length ? pending.sort()[0] : null;
  }, [events]);

  const applyVote = useCallback((result: VoteResult) => {
    setItems((current) =>
      current === null
        ? current
        : current.map((item) =>
            item.id === result.submission_id
              ? { ...item, voted_by_me: result.voted, votes: result.votes }
              : item,
          ),
    );
  }, []);

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-section md:px-6">
      <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <h1 className="text-h1 text-ink-900">Gallery</h1>
        <div className="flex flex-col gap-3 md:flex-row md:items-end">
          <SimpleSelect
            label="Order"
            value={order}
            onChange={(value) => setOrder(value as Order)}
            options={ORDERS}
            triggerClassName="md:w-44"
          />
          <Input
            label="Search"
            placeholder="Search submissions"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="md:w-72"
          />
        </div>
      </div>

      {hiddenUntil && (
        <div className="mb-6">
          <ResultsHiddenNotice hiddenUntil={hiddenUntil} />
        </div>
      )}

      {items === null && !error && <SkeletonRows rows={5} cols={3} />}
      {error && <ErrorState description={error} onRetry={() => setRetryToken((v) => v + 1)} />}

      {items && items.length === 0 && debouncedQ === '' && (
        <EmptyState title="No submissions yet" description="Be the first to submit - your draft saves as you type." />
      )}
      {items && items.length === 0 && debouncedQ !== '' && (
        <EmptyState title="No matches" description={`Nothing matches "${debouncedQ}". Try a different search.`} />
      )}

      {items && items.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {items.map((s) => {
            const event = eventById.get(s.event_id);
            return (
              <Card
                key={s.id}
                title={
                  <Link to={`/submissions/${s.id}`} className="hover:text-brand-500">
                    {s.title}
                  </Link>
                }
                meta={s.track}
                footer={
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Link to={`/submissions/${s.id}`} className="text-meta text-brand-500">
                      {s.comment_count === 0
                        ? 'Add the first comment'
                        : `${s.comment_count} comment${s.comment_count === 1 ? '' : 's'}`}
                    </Link>
                    {user ? (
                      <VoteButton
                        submissionId={s.id}
                        voted={s.voted_by_me}
                        votes={s.votes}
                        votingEnabled={event?.voting_enabled ?? false}
                        onChange={applyVote}
                        onError={(message) => setToast({ message, ok: false })}
                      />
                    ) : (
                      event?.voting_enabled && (
                        <Link to="/login?next=/gallery" className="text-meta text-brand-500">
                          Log in to vote
                        </Link>
                      )
                    )}
                  </div>
                }
              >
                <p className="line-clamp-4 text-body text-ink-600">{s.description}</p>
                {s.votes === null && event?.voting_enabled && (
                  <p className="mt-3">
                    <Badge status="info">Counts hidden until voting closes</Badge>
                  </p>
                )}
              </Card>
            );
          })}
        </div>
      )}

      <ToastRegion>
        {toast && <Toast status={toast.ok ? 'success' : 'danger'} message={toast.message} onDismiss={() => setToast(null)} />}
      </ToastRegion>
    </div>
  );
}
