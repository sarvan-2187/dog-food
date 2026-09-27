import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { DeadlineCountdown } from '../components/DeadlineCountdown';
import { ErrorState, InlineStatus, SkeletonRows } from '../components/feedback';
import { Button, Card, Input } from '../components/ui';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import type { EventRecord, Team } from '../types';

export function EventDetailPage() {
  const { slug = '' } = useParams();
  const { user } = useAuth();
  const [event, setEvent] = useState<EventRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [myTeam, setMyTeam] = useState<Team | null>(null);

  useEffect(() => {
    api
      .get<EventRecord>(`/api/events/${slug}`)
      .then(setEvent)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load this event.'));
  }, [slug]);

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
      </div>

      {user?.role === 'participant' && (
        <Card title="Your team">{myTeam ? <TeamCard team={myTeam} /> : <TeamFormation eventId={event.id} onTeam={setMyTeam} />}</Card>
      )}

      {myTeam && (
        <Link to={`/teams/${myTeam.id}/submission`}>
          <Button variant="primary">Go to your submission</Button>
        </Link>
      )}

      {(user?.role === 'organizer' || user?.role === 'admin') && (
        <Card title="Organizing this event">
          <div className="flex flex-wrap gap-2">
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

  return (
    <div className="flex flex-col gap-3">
      <p className="text-h3 text-ink-800">{team.name}</p>
      <p className="text-meta text-ink-500">{team.members.map((m) => m.name).join(', ')}</p>
      <div className="flex flex-col gap-2 md:flex-row md:items-end">
        <Input label="Invite link" readOnly value={inviteUrl} className="flex-1" />
        <Button variant="secondary" onClick={copy}>
          {copied ? 'Copied' : 'Copy'}
        </Button>
      </div>
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
