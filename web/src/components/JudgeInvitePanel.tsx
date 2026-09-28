import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Badge, Button, Card, Input, SimpleSelect } from './ui';
import { EmptyState, SkeletonRows } from './feedback';
import { ApiError, api } from '../lib/api';
import type { JudgeInvite } from '../types';

const EXPIRY_OPTIONS = [
  { value: '7', label: '7 days' },
  { value: '14', label: '14 days' },
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
];

const STATUS_TONE: Record<JudgeInvite['status'], 'success' | 'warning' | 'neutral'> = {
  redeemed: 'success',
  open: 'warning',
  expired: 'neutral',
};

/**
 * Organizer-facing judge invitation management (PLAN.md T2: "judge invitation
 * and assignment").
 *
 * `judge` is the one role with no self-service signup — a self-serve judge
 * account would hand anyone sight of every score — so this panel is the only
 * route into it.
 */
export function JudgeInvitePanel({ onToast }: { onToast: (message: string, ok: boolean) => void }) {
  const [invites, setInvites] = useState<JudgeInvite[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [note, setNote] = useState('');
  const [expiry, setExpiry] = useState('14');
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState<number | null>(null);

  const load = useCallback(() => {
    setError(null);
    api
      .get<JudgeInvite[]>('/api/judge-invites')
      .then(setInvites)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load invitations.'));
  }, []);

  useEffect(load, [load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      await api.post<JudgeInvite>('/api/judge-invites', {
        invited_email: email.trim() || null,
        note: note.trim(),
        expires_in_days: Number(expiry),
      });
      setEmail('');
      setNote('');
      onToast('Invitation created. Copy the link and send it to your judge.', true);
      load();
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Could not create the invitation.', false);
    } finally {
      setCreating(false);
    }
  }

  async function copy(invite: JudgeInvite) {
    const url = `${window.location.origin}/judge-invite/${invite.token}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(invite.id);
      window.setTimeout(() => setCopied(null), 2000);
    } catch {
      onToast('Could not reach the clipboard — the link is shown in full below.', false);
    }
  }

  async function revoke(invite: JudgeInvite) {
    try {
      await api.del(`/api/judge-invites/${invite.id}`);
      onToast('Invitation revoked. That link no longer works.', true);
      load();
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Could not revoke that invitation.', false);
    }
  }

  return (
    <Card title="Judges" meta={invites ? `${invites.length} invitation${invites.length === 1 ? '' : 's'}` : undefined}>
      <div className="flex flex-col gap-6">
        <p className="text-body text-ink-600">
          Judges can only join by invitation — there is no public sign-up for the role, since a judge can see
          scores. Send someone a link and they become a judge when they accept it.
        </p>

        <form className="flex flex-col gap-3" onSubmit={create}>
          <div className="grid gap-3 md:grid-cols-2">
            <Input
              label="Their email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              hint="Optional — for your own records. They can accept with any account."
            />
            <SimpleSelect label="Expires in" value={expiry} onChange={setExpiry} options={EXPIRY_OPTIONS} />
          </div>
          <Input
            label="Note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            hint="Optional, e.g. which track they're covering."
          />
          <div>
            <Button type="submit" variant="primary" loading={creating} loadingLabel="Creating...">
              Create invitation
            </Button>
          </div>
        </form>

        {invites === null && !error && <SkeletonRows rows={3} cols={3} />}
        {error && (
          <p role="alert" className="text-meta text-danger-fg">
            {error}
          </p>
        )}

        {invites && invites.length === 0 && (
          <EmptyState
            title="No invitations yet"
            description="Create one above to bring your first judge onto the event."
          />
        )}

        {invites && invites.length > 0 && (
          <ul className="flex flex-col divide-y divide-border-subtle">
            {invites.map((invite) => (
              <li key={invite.id} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-label text-ink-800">
                    {invite.invited_email || <span className="text-ink-500">No email recorded</span>}
                  </span>
                  {/* Status is carried by the word, not the colour (PLAN.md 4.5). */}
                  <Badge status={STATUS_TONE[invite.status]}>
                    {invite.status === 'redeemed'
                      ? `Accepted by ${invite.redeemed_by_name ?? 'a judge'}`
                      : invite.status === 'expired'
                        ? 'Expired'
                        : 'Awaiting acceptance'}
                  </Badge>
                </div>

                {invite.note && <p className="text-meta text-ink-600">{invite.note}</p>}

                <p className="text-meta text-ink-500">
                  {invite.status === 'redeemed'
                    ? `Accepted ${new Date(invite.redeemed_at as string).toLocaleString()}`
                    : `Expires ${new Date(invite.expires_at).toLocaleString()}`}
                </p>

                {invite.status === 'open' && (
                  <div className="flex flex-wrap items-center gap-2">
                    <code className="min-w-0 flex-1 truncate rounded-sm bg-surface-100 px-2 py-1 text-meta text-ink-700">
                      {`${window.location.origin}/judge-invite/${invite.token}`}
                    </code>
                    <Button variant="secondary" size="sm" onClick={() => copy(invite)}>
                      {copied === invite.id ? 'Copied' : 'Copy link'}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => revoke(invite)}>
                      Revoke
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
