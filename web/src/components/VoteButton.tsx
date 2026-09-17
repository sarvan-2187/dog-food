import { useState } from 'react';
import { Button } from './ui';
import { ApiError, api } from '../lib/api';
import type { VoteResult } from '../types';

/**
 * Optimistic toggle with a visible rollback on rejection (PLAN.md 4.6: fine for
 * a low-risk action, provided it rolls back visibly).
 */
export function VoteButton({
  submissionId,
  voted,
  votes,
  votingEnabled,
  onChange,
  onError,
}: {
  submissionId: number;
  voted: boolean;
  /** null while results are hidden - show no number rather than a wrong one. */
  votes: number | null;
  votingEnabled: boolean;
  onChange: (next: VoteResult) => void;
  onError: (message: string) => void;
}) {
  const [pending, setPending] = useState(false);

  async function toggle() {
    if (pending) return;
    const before = { voted, votes };
    // Optimistic: flip immediately so the control feels instant.
    onChange({
      submission_id: submissionId,
      voted: !voted,
      votes: votes === null ? null : votes + (voted ? -1 : 1),
    });
    setPending(true);
    try {
      const result = voted
        ? await api.del<VoteResult>(`/api/submissions/${submissionId}/vote`)
        : await api.post<VoteResult>(`/api/submissions/${submissionId}/vote`);
      onChange(result);
    } catch (err) {
      // Roll back visibly, and say why in words.
      onChange({ submission_id: submissionId, voted: before.voted, votes: before.votes });
      onError(err instanceof ApiError ? err.message : 'Your vote could not be saved.');
    } finally {
      setPending(false);
    }
  }

  if (!votingEnabled) return null;

  return (
    <Button
      variant={voted ? 'primary' : 'secondary'}
      size="sm"
      onClick={toggle}
      aria-pressed={voted}
      // The state is carried by the word, not only by the fill colour (4.5).
      aria-label={voted ? 'Remove your vote' : 'Vote for this submission'}
    >
      <span aria-hidden="true">{voted ? '♥' : '♡'}</span>
      {voted ? 'Voted' : 'Vote'}
      {votes !== null && <span className="tabular ml-1 opacity-70">{votes}</span>}
    </Button>
  );
}
