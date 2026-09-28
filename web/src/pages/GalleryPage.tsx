import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ResultsHiddenNotice } from '../components/ResultsHiddenNotice';
import { VoteButton } from '../components/VoteButton';
import { EmptyState, ErrorState, SkeletonRows, Toast, ToastRegion } from '../components/feedback';
import { Badge, Card, Input, SimpleSelect } from '../components/ui';
import { EventStatusBadge } from './EventsPage';
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

/**
 * Doubles as two routes. "/gallery", with no :slug, is an event picker: a
 * grid of hackathon cards, since a flat cross-event submission list stopped
 * making sense once more than one hackathon can run at a time - a visitor
 * thinks "which event's gallery" before "which submission". Clicking a card
 * goes to "/events/:slug/gallery", which is this same component with :slug
 * set, rendering the actual searchable/sortable submissions grid for that
 * one event.
 */
export function GalleryPage() {
  const { slug } = useParams();
  const { user } = useAuth();
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [order, setOrder] = useState<Order>('recent');
  const [items, setItems] = useState<GalleryItem[] | null>(null);
  const [events, setEvents] = useState<EventRecord[] | null>(null);
  const [scopedEvent, setScopedEvent] = useState<EventRecord | null>(null);
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
    if (slug) {
      api.get<EventRecord>(`/api/events/${slug}`).then(setScopedEvent).catch(() => setScopedEvent(null));
    } else {
      api
        .get<EventRecord[]>('/api/events')
        .then(setEvents)
        .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load events.'));
    }
  }, [slug]);

  useEffect(() => {
    if (!slug) return; // the picker view needs no submissions - only the event list above
    if (!scopedEvent) return; // wait for the scoped event to resolve before fetching its gallery
    setItems(null);
    setError(null);
    const params = new URLSearchParams({ order, event_id: String(scopedEvent.id) });
    if (debouncedQ) params.set('q', debouncedQ);
    if (order === 'random') params.set('seed', String(seed));
    api
      .get<GalleryItem[]>(`/api/gallery?${params}`)
      .then(setItems)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load the gallery.'));
  }, [debouncedQ, order, seed, retryToken, slug, scopedEvent]);

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

  // "/gallery" itself: pick a hackathon, then see its gallery.
  if (!slug) {
    return (
      <div className="mx-auto max-w-[1200px] px-4 py-section md:px-6">
        <div className="mb-6">
          <h1 className="text-h1 text-ink-900">Gallery</h1>
          <p className="mt-1 text-meta text-ink-500">Pick a hackathon to see what its teams submitted.</p>
        </div>
        {events === null && !error && <SkeletonRows rows={4} cols={3} />}
        {error && <ErrorState description={error} onRetry={() => setRetryToken((v) => v + 1)} />}
        {events && events.length === 0 && (
          <EmptyState title="No events yet" description="Check back once a hackathon has been scheduled." />
        )}
        {events && events.length > 0 && (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {events.map((e) => (
              <Link key={e.id} to={`/events/${e.slug}/gallery`} className="h-full">
                <Card title={e.name} meta={<EventStatusBadge event={e} />}>
                  <p className="line-clamp-3 text-body text-ink-600">{e.description || 'No description yet.'}</p>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-section md:px-6">
      <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <Link to={`/events/${slug}`} className="text-meta text-brand-500">
            ← {scopedEvent?.name ?? 'Back to event'}
          </Link>
          <h1 className="text-h1 text-ink-900">{scopedEvent ? `${scopedEvent.name} gallery` : 'Gallery'}</h1>
        </div>
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

      {scopedEvent?.results_hidden_until && new Date(scopedEvent.results_hidden_until).getTime() > Date.now() && (
        <div className="mb-6">
          <ResultsHiddenNotice hiddenUntil={scopedEvent.results_hidden_until} />
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
          {items.map((s) => (
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
                      votingEnabled={scopedEvent?.voting_enabled ?? false}
                      onChange={applyVote}
                      onError={(message) => setToast({ message, ok: false })}
                    />
                  ) : (
                    scopedEvent?.voting_enabled && (
                      <Link to={`/login?next=/events/${slug}/gallery`} className="text-meta text-brand-500">
                        Log in to vote
                      </Link>
                    )
                  )}
                </div>
              }
            >
              <div className="mb-3 aspect-video overflow-hidden rounded-md bg-surface-100">
                {s.image_url ? (
                  <img src={s.image_url} alt="" className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full w-full items-center justify-center text-meta text-ink-500">No image</div>
                )}
              </div>
              <p className="line-clamp-4 text-body text-ink-600">{s.description}</p>
              {s.votes === null && scopedEvent?.voting_enabled && (
                <p className="mt-3">
                  <Badge status="info">Counts hidden until voting closes</Badge>
                </p>
              )}
            </Card>
          ))}
        </div>
      )}

      <ToastRegion>
        {toast && <Toast status={toast.ok ? 'success' : 'danger'} message={toast.message} onDismiss={() => setToast(null)} />}
      </ToastRegion>
    </div>
  );
}
