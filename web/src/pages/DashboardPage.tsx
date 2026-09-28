import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import { eventCover } from '../lib/event-cover';
import type { AuditEntry, EventRecord, GalleryItem, JudgeProgress, Team } from '../types';
import { Badge, Button, Card, MetricTile, RoleBadge } from '../components/ui';
import { EmptyState, ErrorState, SkeletonRows } from '../components/feedback';

/**
 * One /dashboard route, four different landings.
 *
 * Every role previously dropped onto /events after login and had to know for
 * itself where its work lived - a judge's queue is on /judge, an organizer's
 * controls are per-event, a participant's team is on /teams/mine. This routes
 * that knowledge into the product: the panels a role can act on are the panels
 * it gets, and a panel a role can't use is absent rather than disabled
 * (PLAN.md 4.4, same rule the nav follows).
 *
 * Data comes from endpoints that already enforce the role server-side, so a
 * participant hitting /dashboard cannot coax an organizer's panel out of it by
 * editing local state - the API would refuse the fetch regardless.
 */
export function DashboardPage() {
  const { user } = useAuth();
  if (!user) return null;

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-section md:px-6">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-eyebrow uppercase text-ink-400">Dashboard</p>
          <h1 className="mt-1 text-h1 text-ink-900">
            Welcome back, <span className="font-serif italic">{user.name.split(' ')[0]}</span>
          </h1>
        </div>
        <RoleBadge role={user.role} />
      </header>

      {user.role === 'participant' && <ParticipantDashboard />}
      {user.role === 'judge' && <JudgeDashboard />}
      {user.role === 'organizer' && <OrganizerDashboard userId={user.id} />}
      {user.role === 'admin' && <AdminDashboard />}
    </div>
  );
}

/** Shared loading/error/empty plumbing, so each panel below is only its content. */
function useResource<T>(path: string, fallbackMessage: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setError(null);
    setData(null);
    api
      .get<T>(path)
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : fallbackMessage));
  }

  useEffect(load, [path]);
  return { data, error, reload: load };
}

// --- Participant -----------------------------------------------------------

function ParticipantDashboard() {
  const teams = useResource<Team[]>('/api/teams/mine', 'Could not load your teams.');
  const events = useResource<EventRecord[]>('/api/events', 'Could not load events.');
  const gallery = useResource<GalleryItem[]>('/api/gallery', 'Could not load the gallery.');

  const open = (events.data ?? []).filter((e) => new Date(e.end_at).getTime() > Date.now());

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <MetricTile label="Teams you're on" value={teams.data?.length ?? '—'} caption="Across all events" accent />
        <MetricTile label="Open events" value={open.length || '—'} caption="Accepting submissions" />
        <MetricTile label="Projects in gallery" value={gallery.data?.length ?? '—'} caption="Public submissions" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Your teams" footer={<Link to="/teams/mine" className="text-ink-900 underline underline-offset-2">Manage teams</Link>}>
          {teams.error && <ErrorState description={teams.error} onRetry={teams.reload} />}
          {!teams.data && !teams.error && <SkeletonRows rows={3} cols={2} />}
          {teams.data?.length === 0 && (
            <EmptyState
              title="No team yet"
              description="Join an event and form a team to start building."
              action={<Link to="/events"><Button variant="primary">Browse events</Button></Link>}
            />
          )}
          {teams.data && teams.data.length > 0 && (
            <ul className="flex flex-col divide-y divide-border-subtle">
              {teams.data.map((t) => (
                <li key={t.id} className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
                  <div>
                    <p className="text-body text-ink-800">{t.name}</p>
                    <p className="text-meta text-ink-500">
                      {t.members.length} of {t.max_team_size} members
                    </p>
                  </div>
                  <Link to={`/teams/${t.id}/submission`} className="text-meta text-ink-900 underline underline-offset-2">
                    Submission
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Open right now" footer={<Link to="/events" className="text-ink-900 underline underline-offset-2">All events</Link>}>
          {events.error && <ErrorState description={events.error} onRetry={events.reload} />}
          {!events.data && !events.error && <SkeletonRows rows={3} cols={2} />}
          {events.data && open.length === 0 && (
            <EmptyState title="Nothing open" description="No event is currently accepting submissions." />
          )}
          {open.length > 0 && (
            <ul className="flex flex-col gap-3">
              {open.slice(0, 4).map((e) => (
                <li key={e.id}>
                  <Link to={`/events/${e.slug}`} className="flex items-center gap-3 rounded-md p-2 transition-colors duration-fast hover:bg-surface-100">
                    <img src={eventCover(e)} alt="" className="h-12 w-20 shrink-0 rounded object-cover" />
                    <span>
                      <span className="block text-body text-ink-800">{e.name}</span>
                      <span className="block text-meta text-ink-500">
                        Closes {new Date(e.end_at).toLocaleDateString()}
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

// --- Judge -----------------------------------------------------------------

function JudgeDashboard() {
  const progress = useResource<JudgeProgress>('/api/judge/assignments', 'Could not load your assignments.');
  const p = progress.data;
  const remaining = p ? p.total - p.completed : null;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <MetricTile label="Still to score" value={remaining ?? '—'} caption="Assigned to you" accent />
        <MetricTile label="Scored" value={p?.completed ?? '—'} caption="Submitted and locked" />
        <MetricTile label="Total assigned" value={p?.total ?? '—'} caption="This round" />
      </div>

      <Card
        title="Your scoring queue"
        meta={p ? `${p.completed}/${p.total} done` : undefined}
        footer={<Link to="/judge" className="text-ink-900 underline underline-offset-2">Full judging view</Link>}
      >
        {progress.error && <ErrorState description={progress.error} onRetry={progress.reload} />}
        {!p && !progress.error && <SkeletonRows rows={4} cols={2} />}
        {p && p.pending.length === 0 && (
          <EmptyState title="Queue clear" description="Every submission assigned to you has been scored." />
        )}
        {p && p.pending.length > 0 && (
          <ul className="flex flex-col divide-y divide-border-subtle">
            {p.pending.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
                <span className="text-body text-ink-800">{a.submission_title}</span>
                <Link to={`/assignments/${a.id}/score`}>
                  <Button variant="secondary">Score</Button>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

// --- Organizer -------------------------------------------------------------

function OrganizerDashboard({ userId }: { userId: number }) {
  const events = useResource<EventRecord[]>('/api/events', 'Could not load events.');
  const mine = (events.data ?? []).filter((e) => e.created_by_id === userId);
  const live = mine.filter((e) => new Date(e.end_at).getTime() > Date.now());

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <MetricTile label="Events you run" value={mine.length || '—'} caption="You created these" accent />
        <MetricTile label="Running" value={live.length} caption="Before the deadline" />
        <MetricTile label="Wrapped" value={mine.length - live.length} caption="Deadline passed" />
      </div>

      <Card
        title="Your events"
        footer={<Link to="/events/new" className="text-ink-900 underline underline-offset-2">Create another event</Link>}
      >
        {events.error && <ErrorState description={events.error} onRetry={events.reload} />}
        {!events.data && !events.error && <SkeletonRows rows={3} cols={3} />}
        {events.data && mine.length === 0 && (
          <EmptyState
            title="No events yet"
            description="Create an event to open registration and start collecting submissions."
            action={<Link to="/events/new"><Button variant="primary">Create event</Button></Link>}
          />
        )}
        {mine.length > 0 && (
          <ul className="flex flex-col gap-4">
            {mine.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center gap-4 rounded-lg border border-border-subtle p-3">
                <img src={eventCover(e)} alt="" className="h-16 w-28 shrink-0 rounded object-cover" />
                <div className="min-w-[12rem] flex-1">
                  <Link to={`/events/${e.slug}`} className="text-body text-ink-800 underline-offset-2 hover:underline">
                    {e.name}
                  </Link>
                  <p className="text-meta text-ink-500">
                    {new Date(e.start_at).toLocaleDateString()} – {new Date(e.end_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Link to={`/events/${e.slug}/rubric`}><Button variant="secondary">Rubric</Button></Link>
                  <Link to={`/events/${e.slug}/settings`}><Button variant="secondary">Settings</Button></Link>
                  <Link to={`/events/${e.slug}/results`}><Button variant="secondary">Results</Button></Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

// --- Admin -----------------------------------------------------------------

function AdminDashboard() {
  const events = useResource<EventRecord[]>('/api/events', 'Could not load events.');
  const audit = useResource<AuditEntry[]>('/api/audit', 'Could not load the audit log.');

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <MetricTile label="Events" value={events.data?.length ?? '—'} caption="Across the platform" accent />
        <MetricTile label="Audit entries" value={audit.data?.length ?? '—'} caption="Most recent first" />
        <MetricTile
          label="Running"
          value={(events.data ?? []).filter((e) => new Date(e.end_at).getTime() > Date.now()).length}
          caption="Before the deadline"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="All events" footer={<Link to="/events" className="text-ink-900 underline underline-offset-2">Events</Link>}>
          {events.error && <ErrorState description={events.error} onRetry={events.reload} />}
          {!events.data && !events.error && <SkeletonRows rows={4} cols={2} />}
          {events.data && (
            <ul className="flex flex-col divide-y divide-border-subtle">
              {events.data.map((e) => (
                <li key={e.id} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                  <Link to={`/events/${e.slug}`} className="text-body text-ink-800 underline-offset-2 hover:underline">
                    {e.name}
                  </Link>
                  <Badge status={new Date(e.end_at).getTime() < Date.now() ? 'danger' : 'info'}>
                    {new Date(e.end_at).getTime() < Date.now() ? 'Closed' : 'Open'}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Recent activity" meta="Audit log">
          {audit.error && <ErrorState description={audit.error} onRetry={audit.reload} />}
          {!audit.data && !audit.error && <SkeletonRows rows={5} cols={2} />}
          {audit.data?.length === 0 && <EmptyState title="Nothing logged yet" description="Actions appear here as they happen." />}
          {audit.data && audit.data.length > 0 && (
            <ul className="flex flex-col divide-y divide-border-subtle">
              {audit.data.slice(0, 8).map((a) => (
                <li key={a.id} className="flex items-baseline justify-between gap-3 py-2 first:pt-0 last:pb-0">
                  <span className="font-mono text-meta text-ink-800">{a.action}</span>
                  <span className="shrink-0 text-meta text-ink-500">
                    {new Date(a.created_at).toLocaleString()}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
