import { useEffect, useState } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { ErrorState, SkeletonRows } from '../components/feedback';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import type { Team } from '../types';

export function JoinTeamPage() {
  const { code = '' } = useParams();
  const { user, status } = useAuth();
  const [team, setTeam] = useState<Team | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status !== 'ready' || !user) return;
    api
      .post<Team>('/api/teams/join', { invite_code: code })
      .then(setTeam)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not join that team.'));
  }, [status, user, code]);

  if (status === 'loading') return null;
  if (!user) return <Navigate to={`/login?next=/join/${code}`} replace />;
  if (error) {
    return (
      <div className="mx-auto max-w-md px-4 py-section">
        <ErrorState description={error} />
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
  return <Navigate to="/events" replace />;
}
