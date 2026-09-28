import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { EmptyState, ErrorState, SkeletonRows } from '../components/feedback';
import { Card } from '../components/ui';
import { ApiError, api } from '../lib/api';
import type { Team } from '../types';

export function TeamsMinePage() {
  const [teams, setTeams] = useState<Team[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Team[]>('/api/teams/mine')
      .then(setTeams)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load your teams.'));
  }, []);

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-section md:px-6">
      <h1 className="mb-6 text-h1 text-ink-900">My teams</h1>
      {teams === null && !error && <SkeletonRows rows={3} cols={2} />}
      {error && <ErrorState description={error} />}
      {teams && teams.length === 0 && <EmptyState title="No teams yet" description="Join an event and create or join a team to get started." />}
      {teams && teams.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2">
          {teams.map((t) => (
            <Link key={t.id} to={`/teams/${t.id}/submission`} className="h-full">
              <Card title={t.name} meta={`${t.members.length} member${t.members.length === 1 ? '' : 's'}`}>
                <p className="text-body text-ink-600">{t.members.map((m) => m.name).join(', ')}</p>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
