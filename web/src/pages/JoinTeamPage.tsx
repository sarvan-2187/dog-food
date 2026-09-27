import { useEffect, useRef, useState } from 'react';
import { Link, Navigate, useParams } from 'react-router-dom';
import { ErrorState, SkeletonRows } from '../components/feedback';
import { Button, Card } from '../components/ui';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import type { Team } from '../types';

export function JoinTeamPage() {
  const { code = '' } = useParams();
  const { user, status } = useAuth();
  const [team, setTeam] = useState<Team | null>(null);
  const [alreadyMember, setAlreadyMember] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Redeeming an invite is a write. StrictMode mounts effects twice in dev, and
  // a second POST would come back 409 and read as a failure, so the request is
  // fired at most once per code.
  const attempted = useRef<string | null>(null);

  useEffect(() => {
    if (status !== 'ready' || !user) return;
    if (attempted.current === code) return;
    attempted.current = code;

    api
      .post<Team>('/api/teams/join', { invite_code: code })
      .then(setTeam)
      .catch(async (err) => {
        // Following your own invite link twice is a normal thing to do, not an
        // error: land on the team instead of a dead end.
        if (err instanceof ApiError && err.status === 409) {
          setAlreadyMember(true);
          try {
            const mine = await api.get<Team[]>('/api/teams/mine');
            const match = mine.find((t) => t.invite_code === code);
            if (match) {
              setTeam(match);
              return;
            }
          } catch {
            // fall through to the generic message below
          }
        }
        setError(err instanceof ApiError ? err.message : 'Could not join that team.');
      });
  }, [status, user, code]);

  if (status === 'loading') return null;
  if (!user) return <Navigate to={`/login?next=/join/${code}`} replace />;

  if (error) {
    return (
      <div className="mx-auto max-w-md px-4 py-section">
        <ErrorState title="That invite did not work" description={error} />
        <p className="mt-4 text-center text-meta">
          <Link to="/events" className="text-brand-500">
            Browse events
          </Link>
        </p>
      </div>
    );
  }

  if (!team) {
    return (
      <div className="mx-auto max-w-md px-4 py-section">
        <SkeletonRows rows={3} cols={1} />
      </div>
    );
  }

  // An explicit success screen, never a silent redirect (PLAN.md Phase 1 UX).
  return (
    <div className="mx-auto max-w-md px-4 py-section">
      <Card title={alreadyMember ? "You're already on this team" : "You're in"}>
        <div className="flex flex-col gap-4">
          <p className="text-body text-ink-700">
            {alreadyMember ? 'You were already a member of ' : 'You have joined '}
            <strong className="text-ink-900">{team.name}</strong>.
          </p>
          <p className="text-meta text-ink-500">
            {team.members.length} member{team.members.length === 1 ? '' : 's'}:{' '}
            {team.members.map((m) => m.name).join(', ')}
          </p>
          <Link to={`/teams/${team.id}/submission`}>
            <Button variant="primary" className="w-full">
              Go to your submission
            </Button>
          </Link>
          <Link to="/teams/mine" className="text-center text-meta text-brand-500">
            View all my teams
          </Link>
        </div>
      </Card>
    </div>
  );
}
