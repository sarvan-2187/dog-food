import { useCallback, useEffect, useMemo, useState } from 'react';
import { ProjectLinks } from '../components/EventSections';
import { TechTags } from '../components/ProjectExtras';
import { Link, useParams } from 'react-router-dom';
import { ResultsHiddenNotice } from '../components/ResultsHiddenNotice';
import { EmailVoteGate, VoteControl, canVote, useVoter } from '../components/VoteButton';
import { EmptyState, ErrorState, SkeletonRows, Toast, ToastRegion } from '../components/feedback';
import { Badge, Card, Input, SimpleSelect } from '../components/ui';
import { EventStatusBadge } from './EventsPage';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import { gallerySeed } from '../lib/gallery-seed';
import type { EventRecord, GalleryItem, VoteResult } from '../types';

type Order = 'recent' | 'random' | 'votes';

// Radix Select can't hold an empty value, so "no filter" gets a sentinel.
const ALL = '__all__';

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
  const voter = useVoter();
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  // null until the visitor picks an order themselves; see `order` below.
  const [chosenOrder, setChosenOrder] = useState<Order | null>(null);
  const [track, setTrack] = useState(ALL);
  const [tag, setTag] = useState(ALL);
  const [tags, setTags] = useState<string[]>([]);
  const [items, setItems] = useState<GalleryItem[] | null>(null);
  const [events, setEvents] = useState<EventRecord[] | null>(null);
  const [scopedEvent, setScopedEvent] = useState<EventRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);

  // One seed for the whole browser session, so a shuffled gallery does not
  // rearrange itself every time the visitor comes back (PLAN.md Phase 3 UX).
  const seed = useMemo(() => gallerySeed(), []);
  // While an event takes votes its ballot is shuffled by default (DOGFOOD T3),
  // so no entry gets the top of the page just for submitting early or late. The
  // seed above keeps that shuffle stable for each visitor. Events without voting
  // keep "Most recent".
  const order: Order = chosenOrder ?? (scopedEvent?.voting_enabled ? 'random' : 'recent');

  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedQ(q), 300);
    return () => window.clearTimeout(id);
  }, [q]);

  useEffect(() => {
    setChosenOrder(null);
    setTrack(ALL);
    setTag(ALL);
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
    // Filtered on the server, like search, so a filter never hides an entry
    // the page merely hasn't loaded.
    if (track !== ALL) params.set('track', track);
    if (tag !== ALL) params.set('tag', tag);
    if (order === 'random') params.set('seed', String(seed));
    api
      .get<GalleryItem[]>(`/api/gallery?${params}`)
      .then(setItems)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load the gallery.'));
  }, [debouncedQ, order, track, tag, seed, retryToken, slug, scopedEvent]);

  useEffect(() => {
    if (!scopedEvent) return;
    api
      .get<string[]>(`/api/gallery/tags?event_id=${scopedEvent.id}`)
      .then(setTags)
      .catch(() => setTags([]));
  }, [scopedEvent]);

  const filtered = debouncedQ !== '' || track !== ALL || tag !== ALL;

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
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <Link to={`/events/${slug}`} className="text-meta text-brand-500">
            ← {scopedEvent?.name ?? 'Back to event'}
          </Link>
          <h1 className="text-h1 text-ink-900">{scopedEvent ? `${scopedEvent.name} gallery` : 'Gallery'}</h1>
        </div>
        <div className="flex min-w-0 flex-col gap-3 md:flex-row md:flex-wrap md:items-end lg:justify-end">
          <SimpleSelect
            label="Order"
            value={order}
            onChange={(value) => setChosenOrder(value as Order)}
            options={ORDERS}
            triggerClassName="md:w-44"
          />
          {scopedEvent && scopedEvent.tracks.length > 0 && (
            <SimpleSelect
              label="Track"
              value={track}
              onChange={setTrack}
              options={[{ value: ALL, label: 'All tracks' }, ...scopedEvent.tracks.map((t) => ({ value: t, label: t }))]}
              triggerClassName="md:w-44"
            />
          )}
          {tags.length > 0 && (
            <SimpleSelect
              label="Tech tag"
              value={tag}
              onChange={setTag}
              options={[{ value: ALL, label: 'All tags' }, ...tags.map((t) => ({ value: t, label: t }))]}
              triggerClassName="md:w-40"
            />
          )}
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

      {scopedEvent?.voting_enabled && scopedEvent.voting_access === 'email' && !canVote(scopedEvent, !!user, voter) && (
        <div className="mb-6">
          <EmailVoteGate eventId={scopedEvent.id} onToast={(message, ok) => setToast({ message, ok })} />
        </div>
      )}

      {items === null && !error && <SkeletonRows rows={5} cols={3} />}
      {error && <ErrorState description={error} onRetry={() => setRetryToken((v) => v + 1)} />}

      {items && items.length === 0 && !filtered && (
        <EmptyState title="No submissions yet" description="Be the first to submit - your draft saves as you type." />
      )}
      {items && items.length === 0 && filtered && (
        <EmptyState
          title="No matches"
          description={
            debouncedQ !== ''
              ? `Nothing matches "${debouncedQ}" with these filters. Try a different search or filter.`
              : 'Nothing matches these filters. Try a different track or tag.'
          }
        />
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
                  <VoteControl
                    event={scopedEvent}
                    signedIn={!!user}
                    voter={voter}
                    loginNext={`/events/${slug}/gallery`}
                    submissionId={s.id}
                    voted={s.voted_by_me}
                    votes={s.votes}
                    onChange={applyVote}
                    onError={(message) => setToast({ message, ok: false })}
                  />
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
              {s.awards.length > 0 && (
                <p className="mb-2 flex flex-wrap gap-1.5">
                  {s.awards.map((a) => (
                    <Badge key={a} status="success">{a}</Badge>
                  ))}
                </p>
              )}
              {s.tagline && <p className="mb-2 text-body font-medium text-ink-800">{s.tagline}</p>}
              <p className="line-clamp-4 text-body text-ink-600">{s.description}</p>
              {s.tech_tags.length > 0 && (
                <div className="mt-3">
                  <TechTags tags={s.tech_tags} />
                </div>
              )}
              {(s.repo_url || s.demo_url || s.video_url) && (
                <p className="mt-3">
                  <ProjectLinks repo={s.repo_url} demo={s.demo_url} video={s.video_url} />
                </p>
              )}
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
