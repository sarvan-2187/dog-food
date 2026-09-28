import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import { eventCover } from '../lib/event-cover';
import type { Announcement, AuditEntry, EventRecord, GalleryItem, JudgeProgress, Team, User } from '../types';
import { Button, Card, MetricTile } from '../components/ui';
import { EmptyState, ErrorState, SkeletonRows } from '../components/feedback';
import { EmailDeliveryPanel, HelpSignInPanel } from '../components/AccountRecoveryPanels';
import { JudgingEvents } from './JudgeDashboardPage';
import { PhaseBadge, eventPhase } from '../components/EventTimeline';
import type { EventPhase } from '../components/EventTimeline';

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
 * Layout: a welcome header, three headline numbers, then the work itself in a
 * two-thirds column with supporting panels in a one-third column beside it.
 *
 * Data comes from endpoints that already enforce the role server-side, so a
 * participant hitting /dashboard cannot coax an organizer's panel out of it by
 * editing local state - the API would refuse the fetch regardless.
 */
export function DashboardPage() {
  const { user } = useAuth();
  if (!user) return null;

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-10 md:px-8 md:py-12">
      <Welcome user={user} />
      {user.role === 'participant' && <ParticipantDashboard />}
      {user.role === 'judge' && <JudgeDashboard />}
      {user.role === 'organizer' && <OrganizerDashboard userId={user.id} />}
      {user.role === 'admin' && <AdminDashboard />}
    </div>
  );
}

const TAGLINE: Record<User['role'], string> = {
  participant: 'Your teams, your deadlines and the latest from your events, all in one place.',
  judge: 'Your scoring queue is below. Score each project on its own merits; HackFlow handles the maths.',
  organizer: 'Everything you run, and the people who need a hand, at a glance.',
  admin: 'The whole platform at a glance: events, activity, and the people who need a hand.',
};

function Welcome({ user }: { user: User }) {
  const first = user.name.split(' ')[0];
  return (
    <header className="mb-10 flex items-center gap-5 md:gap-7">
      {user.avatar_url ? (
        <img src={user.avatar_url} alt="" className="h-16 w-16 shrink-0 rounded-full object-cover md:h-20 md:w-20" />
      ) : (
        <span
          aria-hidden="true"
          className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-brand-500 text-h2 text-surface-0 md:h-20 md:w-20"
        >
          {first.charAt(0).toUpperCase()}
        </span>
      )}
      <div className="min-w-0">
        <h1 className="text-h1 text-ink-900">
          Welcome back, <span className="font-serif italic">{first}</span>
        </h1>
        <p className="mt-2 max-w-2xl text-body-lg text-ink-500">{TAGLINE[user.role]}</p>
      </div>
    </header>
  );
}

/** The two-thirds / one-third grid every role's dashboard sits in. */
function Columns({ main, side }: { main: ReactNode; side: ReactNode }) {
  return (
    <div className="grid items-start gap-6 lg:grid-cols-3">
      <div className="flex min-w-0 flex-col gap-6 lg:col-span-2">{main}</div>
      <div className="flex min-w-0 flex-col gap-6">{side}</div>
    </div>
  );
}

function Metrics({ children }: { children: ReactNode }) {
  return <div className="mb-6 grid gap-4 sm:grid-cols-3">{children}</div>;
}

const panel = 'rounded-xl shadow-sm';

const PHASE_ORDER: EventPhase[] = ['open', 'upcoming', 'judging', 'results'];

/** Live events first, finished ones last, soonest deadline first within each. */
function byPhase(events: EventRecord[]): EventRecord[] {
  const rank = (e: EventRecord) => PHASE_ORDER.indexOf(eventPhase(e));
  return [...events].sort((a, b) => rank(a) - rank(b) || new Date(a.end_at).getTime() - new Date(b.end_at).getTime());
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
    <>
      <Metrics>
        <MetricTile label="Teams you're on" value={teams.data?.length ?? '—'} caption="Across all events" accent />
        <MetricTile label="Open events" value={open.length || '—'} caption="Accepting submissions" />
        <MetricTile label="Projects in gallery" value={gallery.data?.length ?? '—'} caption="Public submissions" />
      </Metrics>
      <Columns
        main={
          <>
            <LatestAnnouncements />
            <Card
              className={panel}
              title="Your teams"
              footer={<Link to="/teams/mine" className="text-ink-900 underline underline-offset-2">Manage teams</Link>}
            >
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
                    <li key={t.id} className="flex items-center justify-between gap-4 py-4 first:pt-0 last:pb-0">
                      <div>
                        <p className="text-body text-ink-800">{t.name}</p>
                        <p className="text-meta text-ink-500">
                          {t.members.length} of {t.max_team_size} members
                        </p>
                      </div>
                      <Link to={`/teams/${t.id}/submission`}>
                        <Button variant="secondary" size="sm">Submission</Button>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </>
        }
        side={
          <Card
            className={panel}
            title="Open right now"
            footer={<Link to="/events" className="text-ink-900 underline underline-offset-2">All events</Link>}
          >
            {events.error && <ErrorState description={events.error} onRetry={events.reload} />}
            {!events.data && !events.error && <SkeletonRows rows={3} cols={2} />}
            {events.data && open.length === 0 && (
              <EmptyState title="Nothing open" description="No event is currently accepting submissions." />
            )}
            {open.length > 0 && (
              <ul className="flex flex-col gap-2">
                {open.slice(0, 5).map((e) => (
                  <li key={e.id}>
                    <Link
                      to={`/events/${e.slug}`}
                      className="flex items-center gap-3 rounded-md p-2 transition-colors duration-fast hover:bg-surface-100"
                    >
                      <img src={eventCover(e)} alt="" className="h-12 w-16 shrink-0 rounded-md object-cover" />
                      <span className="min-w-0">
                        <span className="block truncate text-body text-ink-800">{e.name}</span>
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
        }
      />
    </>
  );
}

// --- Judge -----------------------------------------------------------------

function JudgeDashboard() {
  const progress = useResource<JudgeProgress>('/api/judge/assignments', 'Could not load your assignments.');
  const p = progress.data;
  const remaining = p ? p.total - p.completed : null;

  return (
    <>
      <Metrics>
        <MetricTile label="Still to score" value={remaining ?? '—'} caption="Assigned to you" accent />
        <MetricTile label="Scored" value={p?.completed ?? '—'} caption="Submitted and locked" />
        <MetricTile label="Total assigned" value={p?.total ?? '—'} caption="This round" />
      </Metrics>
      <Columns
        main={
          <Card
            className={panel}
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
                  <li key={a.id} className="flex items-center justify-between gap-4 py-4 first:pt-0 last:pb-0">
                    <span className="text-body text-ink-800">{a.submission_title}</span>
                    <Link to={`/assignments/${a.id}/score`}>
                      <Button variant="secondary">Score</Button>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        }
        side={
          <>
            <JudgingEvents />
            <Card className={panel} title="How scoring works">
              <ul className="flex flex-col gap-3 text-body text-ink-600">
                <li>You only ever see your own scores. Nobody else sees yours.</li>
                <li>Tough or generous, it evens out: each judge is compared with their own average.</li>
                <li>Know the team? Step back from the project's score page.</li>
              </ul>
            </Card>
          </>
        }
      />
    </>
  );
}

// --- Organizer -------------------------------------------------------------

function OrganizerDashboard({ userId }: { userId: number }) {
  const events = useResource<EventRecord[]>('/api/events', 'Could not load events.');
  const mine = byPhase((events.data ?? []).filter((e) => e.created_by_id === userId));
  const count = (...phases: EventPhase[]) => mine.filter((e) => phases.includes(eventPhase(e))).length;

  return (
    <>
      <Metrics>
        <MetricTile label="Open now" value={events.data ? count('open') : '—'} caption="Taking submissions" accent />
        <MetricTile label="Upcoming" value={events.data ? count('upcoming') : '—'} caption="Not started yet" />
        <MetricTile label="Wrapped" value={events.data ? count('judging', 'results') : '—'} caption="Judging or results out" />
      </Metrics>
      <Columns
        main={
          <Card
            className={panel}
            title="Your events"
            meta={events.data ? `${mine.length} event${mine.length === 1 ? '' : 's'}` : undefined}
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
            {mine.length > 0 && <EventRows events={mine} />}
          </Card>
        }
        side={<HelpSignInPanel />}
      />
    </>
  );
}

function EventRows({ events }: { events: EventRecord[] }) {
  return (
    <ul className="flex flex-col divide-y divide-border-subtle">
      {events.map((e) => (
        <li key={e.id} className="flex flex-wrap items-center gap-4 py-4 first:pt-0 last:pb-0">
          <img src={eventCover(e)} alt="" className="h-14 w-20 shrink-0 rounded-md object-cover" />
          <div className="min-w-[10rem] flex-1">
            <span className="flex flex-wrap items-center gap-2">
              <Link to={`/events/${e.slug}`} className="text-body text-ink-800 underline-offset-2 hover:underline">
                {e.name}
              </Link>
              <PhaseBadge event={e} />
            </span>
            <p className="text-meta text-ink-500">
              {new Date(e.start_at).toLocaleDateString()} – {new Date(e.end_at).toLocaleDateString()}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to={`/events/${e.slug}/rubric`}><Button variant="secondary" size="sm">Rubric</Button></Link>
            <Link to={`/events/${e.slug}/settings`}><Button variant="secondary" size="sm">Settings</Button></Link>
            <Link to={`/events/${e.slug}/results`}><Button variant="secondary" size="sm">Results</Button></Link>
          </div>
        </li>
      ))}
    </ul>
  );
}

// --- Admin -----------------------------------------------------------------

function AdminDashboard() {
  const events = useResource<EventRecord[]>('/api/events', 'Could not load events.');
  const audit = useResource<AuditEntry[]>('/api/audit', 'Could not load the audit log.');

  return (
    <>
      <Metrics>
        <MetricTile label="Events" value={events.data?.length ?? '—'} caption="Across the platform" accent />
        <MetricTile label="Audit entries" value={audit.data?.length ?? '—'} caption="Most recent first" />
        <MetricTile
          label="Open now"
          value={events.data ? events.data.filter((e) => eventPhase(e) === 'open').length : '—'}
          caption="Taking submissions"
        />
      </Metrics>
      <Columns
        main={
          <>
            <Card className={panel} title="All events" footer={<Link to="/events" className="text-ink-900 underline underline-offset-2">Events</Link>}>
              {events.error && <ErrorState description={events.error} onRetry={events.reload} />}
              {!events.data && !events.error && <SkeletonRows rows={4} cols={2} />}
              {events.data && (
                <ul className="flex flex-col divide-y divide-border-subtle">
                  {byPhase(events.data).map((e) => (
                    <li key={e.id} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                      <Link to={`/events/${e.slug}`} className="text-body text-ink-800 underline-offset-2 hover:underline">
                        {e.name}
                      </Link>
                      <PhaseBadge event={e} />
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card className={panel} title="Recent activity" meta="Audit log">
              {audit.error && <ErrorState description={audit.error} onRetry={audit.reload} />}
              {!audit.data && !audit.error && <SkeletonRows rows={5} cols={2} />}
              {audit.data?.length === 0 && <EmptyState title="Nothing logged yet" description="Actions appear here as they happen." />}
              {audit.data && audit.data.length > 0 && (
                <ul className="flex flex-col divide-y divide-border-subtle">
                  {audit.data.slice(0, 8).map((a) => (
                    <li key={a.id} className="flex items-baseline justify-between gap-3 py-2 first:pt-0 last:pb-0">
                      <span className="font-mono text-meta text-ink-800">{a.action}</span>
                      <span className="shrink-0 text-meta text-ink-500">{new Date(a.created_at).toLocaleString()}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </>
        }
        side={
          <>
            <HelpSignInPanel />
            <EmailDeliveryPanel />
          </>
        }
      />
    </>
  );
}

/** PLAN.md 10.11: the latest from every event you're on a team in. */
function LatestAnnouncements() {
  const items = useResource<Announcement[]>('/api/announcements/mine', 'Could not load announcements.');
  if (!items.data || items.data.length === 0) return null;
  return (
    <Card className={panel} title="Announcements">
      <ul className="flex flex-col divide-y divide-border-subtle">
        {items.data.map((a) => (
          <li key={a.id} className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0">
            <span className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-label text-ink-900">{a.title}</span>
              <Link to={`/events/${a.event_slug}`} className="text-meta text-brand-500">
                {a.event_name}
              </Link>
            </span>
            <p className="whitespace-pre-line text-body text-ink-700">{a.body}</p>
          </li>
        ))}
      </ul>
    </Card>
  );
}
