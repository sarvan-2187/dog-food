import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import { eventCover } from '../lib/event-cover';
import type { EventRecord } from '../types';
import { Badge, Button, Card } from '../components/ui';
import { EmptyState, ErrorState, SkeletonRows } from '../components/feedback';

export function EventsPage() {
  const { user } = useAuth();
  const [events, setEvents] = useState<EventRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canCreate = user?.role === 'organizer' || user?.role === 'admin';

  function load() {
    setError(null);
    setEvents(null);
    api
      .get<EventRecord[]>('/api/events')
      .then(setEvents)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load events.'));
  }

  useEffect(load, []);

  // The API returns events by start date, which buries what's actually open
  // under last spring's finished ones. Sort so a visitor sees what they can
  // still enter first.
  const ordered = events && [...events].sort((a, b) => {
    const now = Date.now();
    const aOpen = new Date(a.end_at).getTime() > now;
    const bOpen = new Date(b.end_at).getTime() > now;
    if (aOpen !== bOpen) return aOpen ? -1 : 1;
    const at = new Date(a.start_at).getTime();
    const bt = new Date(b.start_at).getTime();
    return aOpen ? at - bt : bt - at;
  });

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-section md:px-6">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-h1 text-ink-900">Events</h1>
          <p className="mt-1 text-body text-ink-500">
            Hackathons running on HackFlow — browse, form a team, and submit.
          </p>
        </div>
        {canCreate && (
          <Link to="/events/new">
            <Button variant="primary">Create event</Button>
          </Link>
        )}
      </div>

      {events === null && !error && <SkeletonRows rows={4} cols={3} />}
      {error && <ErrorState description={error} onRetry={load} />}
      {events && events.length === 0 && (
        <EmptyState
          title="No events yet"
          description={canCreate ? 'Create the first event to get teams building.' : 'Check back soon - nothing has been scheduled yet.'}
          action={
            canCreate ? (
              <Link to="/events/new">
                <Button variant="primary">Create event</Button>
              </Link>
            ) : undefined
          }
        />
      )}
      {events && events.length > 0 && (
        <div data-tour="event-list" className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {ordered!.map((e) => (
            <Link key={e.id} to={`/events/${e.slug}`} className="group h-full">
              <Card
                className="transition-shadow duration-base group-hover:shadow-md"
                title={e.name}
                meta={<EventStatusBadge event={e} />}
                media={
                  /* Fixed 16:9 frame so a row of cards lines up whatever each
                     photo's own aspect ratio happens to be. */
                  <span className="block aspect-video overflow-hidden bg-surface-100">
                    <img
                      src={eventCover(e)}
                      alt=""
                      loading="lazy"
                      className="h-full w-full object-cover transition-transform duration-slow group-hover:scale-[1.03]"
                    />
                  </span>
                }
              >
                <p className="line-clamp-2 text-body text-ink-600">{e.description || 'No description yet.'}</p>
                {e.tracks.length > 0 && (
                  <span className="mt-3 flex flex-wrap gap-1.5">
                    {e.tracks.slice(0, 3).map((t) => (
                      <span key={t} className="rounded-full bg-surface-100 px-2.5 py-1 text-meta text-ink-600">
                        {t}
                      </span>
                    ))}
                  </span>
                )}
                <span className="mt-3 block text-meta text-ink-500">
                  {new Date(e.start_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} –{' '}
                  {new Date(e.end_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
                </span>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

export function EventStatusBadge({ event }: { event: EventRecord }) {
  const passed = new Date(event.end_at).getTime() < Date.now();
  return <Badge status={passed ? 'danger' : 'info'}>{passed ? 'Deadline passed' : 'Open'}</Badge>;
}
