import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ErrorState, SkeletonRows } from '../components/feedback';
import { Button, Card } from '../components/ui';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import type { JudgeInvitePreview, JudgeInviteRedeemResult } from '../types';

/**
 * Redeeming a judge invitation.
 *
 * Unlike the team-invite page this does **not** redeem on mount. Accepting
 * changes the signed-in account's role, which is not something to do to someone
 * because they followed a link — they get told what will happen and press the
 * button (PLAN.md 4.3).
 */
export function JudgeInvitePage() {
  const { token = '' } = useParams();
  const { user, status, refresh } = useAuth();
  const [preview, setPreview] = useState<JudgeInvitePreview | null>(null);
  const [result, setResult] = useState<JudgeInviteRedeemResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [accepting, setAccepting] = useState(false);

  const load = useCallback(() => {
    setError(null);
    api
      .get<JudgeInvitePreview>(`/api/judge-invites/${token}/preview`)
      .then(setPreview)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not check that invitation.'));
  }, [token]);

  useEffect(load, [load]);

  async function accept() {
    setAccepting(true);
    setError(null);
    try {
      const redeemed = await api.post<JudgeInviteRedeemResult>(`/api/judge-invites/${token}/redeem`);
      setResult(redeemed);
      // The nav is role-aware, so the session has to be re-read for "Judging"
      // to appear without a manual reload.
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not accept that invitation.');
    } finally {
      setAccepting(false);
    }
  }

  if (status === 'loading') return null;

  if (error) {
    return (
      <div className="mx-auto max-w-md px-4 py-section">
        <ErrorState title="That invitation did not work" description={error} onRetry={load} />
        <p className="mt-4 text-center text-meta">
          <Link to="/events" className="text-brand-500">
            Browse events
          </Link>
        </p>
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="mx-auto max-w-md px-4 py-section">
        <SkeletonRows rows={3} cols={1} />
      </div>
    );
  }

  // A dead link is explained here rather than at the moment someone presses accept.
  if (!preview.valid) {
    return (
      <div className="mx-auto max-w-md px-4 py-section">
        <Card title="This invitation is no longer valid">
          <div className="flex flex-col gap-4">
            <p className="text-body text-ink-700">{preview.reason}</p>
            <p className="text-meta text-ink-500">
              Judge invitations are single-use and expire. Ask the organizer who sent it for a fresh link.
            </p>
            <Link to="/events">
              <Button variant="secondary" className="w-full">
                Browse events
              </Button>
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  if (result) {
    return (
      <div className="mx-auto max-w-md px-4 py-section">
        <Card title={result.already_a_judge ? "You're already a judge" : "You're a judge now"}>
          <div className="flex flex-col gap-4">
            <p className="text-body text-ink-700">
              {result.already_a_judge
                ? 'This account already had the judge role, so nothing changed and the invitation was left unused.'
                : 'Your account has been given the judge role. Submissions assigned to you will appear on your judging dashboard.'}
            </p>
            <Link to="/judge">
              <Button variant="primary" className="w-full">
                Go to judging
              </Button>
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  // Signed out: an invitation grants a role to a person, so there has to be an
  // account to grant it to. Send them through auth and back here.
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-4 py-section">
        <Card title="You've been invited to judge">
          <div className="flex flex-col gap-4">
            <p className="text-body text-ink-700">
              Sign in or create an account first — the invitation gives the judge role to whichever account
              accepts it, so we need to know which one that is.
            </p>
            <Link to={`/login?next=/judge-invite/${token}`}>
              <Button variant="primary" className="w-full">
                Log in and accept
              </Button>
            </Link>
            <Link
              to={`/register?next=/judge-invite/${token}`}
              className="text-center text-meta text-brand-500"
            >
              I don't have an account yet
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  const isOrganizer = user.role === 'organizer' || user.role === 'admin';

  return (
    <div className="mx-auto max-w-md px-4 py-section">
      <Card title="You've been invited to judge" meta={user.role}>
        <div className="flex flex-col gap-4">
          <p className="text-body text-ink-700">
            Accepting this gives <strong className="text-ink-900">{user.email}</strong> the judge role. You'll be
            able to score the submissions an organizer assigns to you, and nothing else changes about your account.
          </p>

          {/* State the consequence before the irreversible-feeling action (4.3). */}
          {isOrganizer ? (
            <div role="alert" className="rounded-md border border-border bg-warning-bg px-4 py-3 text-body text-warning-fg">
              You're signed in as an {user.role}. Accepting would replace that with the judge role and remove your
              ability to run events, so this has been left alone — sign in as the account that should judge, then
              open this link again.
            </div>
          ) : (
            <p className="text-meta text-ink-500">
              You'll keep your teams and submissions. If you're on a team, you simply won't be assigned your own
              team's entry to judge.
            </p>
          )}

          {preview.expires_at && (
            <p className="text-meta text-ink-500">
              This invitation expires {new Date(preview.expires_at).toLocaleString()}.
            </p>
          )}

          <Button
            variant="primary"
            className="w-full"
            loading={accepting}
            loadingLabel="Accepting..."
            disabled={isOrganizer}
            onClick={accept}
          >
            Accept and become a judge
          </Button>
          <Link to="/events" className="text-center text-meta text-ink-500">
            Not now
          </Link>
        </div>
      </Card>
    </div>
  );
}
