import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { DeadlineCountdown } from '../components/DeadlineCountdown';
import { ErrorState, InlineStatus, SkeletonRows } from '../components/feedback';
import { Button, Card, Input } from '../components/ui';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import type { EventRecord, GalleryItem, Team } from '../types';

export function EventDetailPage() {
  const { slug = '' } = useParams();
  const { user } = useAuth();
  const [event, setEvent] = useState<EventRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [myTeam, setMyTeam] = useState<Team | null>(null);
  const [preview, setPreview] = useState<GalleryItem[] | null>(null);

  useEffect(() => {
    api
      .get<EventRecord>(`/api/events/${slug}`)
      .then(setEvent)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load this event.'));
  }, [slug]);

  useEffect(() => {
    if (!event) return;
    api
      .get<GalleryItem[]>(`/api/gallery?event_id=${event.id}&order=recent`)
      .then((items) => setPreview(items.slice(0, 3)))
      .catch(() => setPreview([]));
  }, [event]);

  useEffect(() => {
    if (!user || user.role !== 'participant' || !event) return;
    api
      .get<Team[]>('/api/teams/mine')
      .then((teams) => setMyTeam(teams.find((t) => t.event_id === event.id) ?? null))
      .catch(() => setMyTeam(null));
  }, [user, event]);

  if (error) {
    return (
      <div className="mx-auto max-w-[1200px] px-4 py-section">
        <ErrorState description={error} />
      </div>
    );
  }
  if (!event) {
    return (
      <div className="mx-auto max-w-[1200px] px-4 py-section">
        <SkeletonRows rows={5} cols={1} />
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1200px] flex-col gap-6 px-4 py-section md:px-6">
      <div>
        <h1 className="text-h1 text-ink-900">{event.name}</h1>
        <p className="mt-2 max-w-prose text-body-lg text-ink-600">{event.description}</p>
        <div className="mt-4">
          <DeadlineCountdown endAt={event.end_at} />
        </div>
        {event.tracks.length > 0 && (
          <p className="mt-3 text-meta text-ink-500">Tracks: {event.tracks.join(', ')}</p>
        )}
        {(event.prize_config.prizes?.length ?? 0) > 0 && (
          <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-meta text-ink-700">
            {event.prize_config.prizes!.map((p, i) => (
              <li key={i}>
                <span className="font-semibold text-ink-900">{p.rank}:</span> {p.reward}
              </li>
            ))}
          </ul>
        )}
      </div>

      {user?.role === 'participant' && (
        <Card title="Your team">{myTeam ? <TeamCard team={myTeam} /> : <TeamFormation eventId={event.id} onTeam={setMyTeam} />}</Card>
      )}

      {myTeam && (
        <Link to={`/teams/${myTeam.id}/submission`}>
          <Button variant="primary">Go to your submission</Button>
        </Link>
      )}

      <Card
        title="Submitted projects"
        meta={
          <Link to={`/events/${event.slug}/gallery`} className="text-brand-500">
            See full gallery →
          </Link>
        }
      >
        {preview === null && <SkeletonRows rows={2} cols={1} />}
        {preview && preview.length === 0 && (
          <p className="text-body text-ink-600">No submissions yet - be the first to submit.</p>
        )}
        {preview && preview.length > 0 && (
          <ul className="flex flex-col divide-y divide-border-subtle">
            {preview.map((s) => (
              <li key={s.id} className="flex flex-wrap items-baseline justify-between gap-2 py-3 first:pt-0 last:pb-0">
                <Link to={`/submissions/${s.id}`} className="text-body font-semibold text-ink-900 hover:text-brand-500">
                  {s.title}
                </Link>
                {s.track && <span className="text-meta text-ink-500">{s.track}</span>}
              </li>
            ))}
          </ul>
        )}
      </Card>

      {(user?.role === 'organizer' || user?.role === 'admin') && (
        <Card title="Organizing this event">
          <div className="flex flex-wrap gap-2">
            <Link to={`/events/${event.slug}/settings`}>
              <Button variant="secondary">Event settings</Button>
            </Link>
            <Link to={`/events/${event.slug}/rubric`}>
              <Button variant="secondary">Judging rubric</Button>
            </Link>
            <Link to={`/events/${event.slug}/results`}>
              <Button variant="primary">Assignments &amp; results</Button>
            </Link>
          </div>
        </Card>
      )}
    </div>
  );
}

function TeamCard({ team }: { team: Team }) {
  const [copied, setCopied] = useState(false);
  const inviteUrl = `${window.location.origin}/join/${team.invite_code}`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  const full = team.members.length >= team.max_team_size;

  return (
    <div className="flex flex-col gap-3">
      <p className="text-h3 text-ink-800">{team.name}</p>
      <p className="text-meta text-ink-500">
        {team.members.length} / {team.max_team_size} members: {team.members.map((m) => m.name).join(', ')}
      </p>
      {full ? (
        <p className="text-meta text-ink-500">This team is full - the invite link is no longer usable.</p>
      ) : (
        <div className="flex flex-col gap-2 md:flex-row md:items-end">
          <Input label="Invite link" readOnly value={inviteUrl} className="flex-1" />
          <Button variant="secondary" onClick={copy}>
            {copied ? 'Copied' : 'Copy'}
          </Button>
        </div>
      )}
      {copied && <InlineStatus state="saved" />}
    </div>
  );
}

function TeamFormation({ eventId, onTeam }: { eventId: number; onTeam: (t: Team) => void }) {
  const [mode, setMode] = useState<'create' | 'join'>('create');
  const [name, setName] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const team =
        mode === 'create'
          ? await api.post<Team>(`/api/events/${eventId}/teams`, { name })
          : await api.post<Team>('/api/teams/join', { invite_code: inviteCode });
      onTeam(team);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={onSubmit}>
      <div className="flex gap-2">
        <Button type="button" variant={mode === 'create' ? 'primary' : 'secondary'} size="sm" onClick={() => setMode('create')}>
          Create a team
        </Button>
        <Button type="button" variant={mode === 'join' ? 'primary' : 'secondary'} size="sm" onClick={() => setMode('join')}>
          Join with a link
        </Button>
      </div>
      {mode === 'create' ? (
        <Input label="Team name" required value={name} onChange={(e) => setName(e.target.value)} hint="3-40 characters." />
      ) : (
        <Input label="Invite code" required value={inviteCode} onChange={(e) => setInviteCode(e.target.value)} />
      )}
      {error && (
        <p role="alert" className="text-meta text-danger-fg">
          {error}
        </p>
      )}
      <Button type="submit" variant="primary" loading={loading} loadingLabel="Saving...">
        {mode === 'create' ? 'Create team' : 'Join team'}
      </Button>
    </form>
  );
}
