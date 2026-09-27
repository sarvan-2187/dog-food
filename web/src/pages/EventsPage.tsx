import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
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

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-section md:px-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-h1 text-ink-900">Events</h1>
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
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {events.map((e) => (
            <Link key={e.id} to={`/events/${e.slug}`}>
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

function EventStatusBadge({ event }: { event: EventRecord }) {
  const passed = new Date(event.end_at).getTime() < Date.now();
  return <Badge status={passed ? 'danger' : 'info'}>{passed ? 'Deadline passed' : 'Open'}</Badge>;
}
