import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Button, Input } from './ui';
import { ApiError, api } from '../lib/api';
import type { EventRecord, VoteResult } from '../types';

/** "email" | "anon" once this browser is a guest voter, else null. */
export function useVoter(): string | null {
  const [voter, setVoter] = useState<string | null>(null);
  useEffect(() => {
    api
      .get<{ voter: string | null }>('/api/voter/me')
      .then((r) => setVoter(r.voter))
      .catch(() => setVoter(null));
  }, []);
  return voter;
}

/** Whether this viewer can press Vote right now, under the event's voting_access. */
export function canVote(event: EventRecord | null | undefined, signedIn: boolean, voter: string | null): boolean {
  if (!event?.voting_enabled) return false;
  if (signedIn || event.voting_access === 'open') return true;
  return event.voting_access === 'email' && voter === 'email';
}

/** Email-confirmed voting: ask for an address, the API emails a link that sets the voter cookie. */
export function EmailVoteGate({ eventId, onToast }: { eventId: number; onToast: (message: string, ok: boolean) => void }) {
  const [email, setEmail] = useState('');
  const [sending, setSending] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSending(true);
    try {
      const r = await api.post<{ detail: string }>(`/api/events/${eventId}/voter-email`, { email });
      onToast(r.detail, true);
      setEmail('');
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'The link could not be sent.', false);
    } finally {
      setSending(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2 md:flex-row md:items-end">
      <Input
        label="Vote without an account"
        type="email"
        required
        placeholder="you@example.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        hint="We email you a link. One vote per project per address."
        className="md:w-72"
      />
      <Button type="submit" variant="secondary" loading={sending} loadingLabel="Sending...">
        Email me a voting link
      </Button>
    </form>
  );
}

/**
 * The vote slot on a gallery card or detail page: the button when this viewer
 * may vote, otherwise what they need to do first. Email-mode pages render one
 * EmailVoteGate of their own, so each card only points at it.
 */
export function VoteControl({
  event,
  signedIn,
  voter,
  loginNext,
  ...button
}: {
  event: EventRecord | null | undefined;
  signedIn: boolean;
  voter: string | null;
  loginNext: string;
} & Omit<Parameters<typeof VoteButton>[0], 'votingEnabled'>) {
  if (!event?.voting_enabled) return null;
  if (canVote(event, signedIn, voter)) return <VoteButton {...button} votingEnabled />;
  if (event.voting_access === 'email') {
    return <span className="text-meta text-ink-500">Confirm your email to vote</span>;
  }
  return (
    <Link to={`/login?next=${loginNext}`} className="text-meta text-brand-500">
      Log in to vote
    </Link>
  );
}

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
