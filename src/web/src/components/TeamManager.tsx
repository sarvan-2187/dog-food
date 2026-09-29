import { useState } from 'react';
import type { FormEvent } from 'react';
import { Badge, Button, Input } from './ui';
import { ApiError, api } from '../lib/api';
import type { Team } from '../types';

/**
 * PLAN.md 10.9. Any member can leave; the captain - whoever created the team -
 * can rename it, remove members, hand the captaincy on and replace the invite
 * link. Every destructive step asks first (the browser's own confirm dialog:
 * keyboard- and screen-reader-accessible for free), and the server refuses all
 * of it after the deadline, which the page says rather than hiding buttons.
 */
export function TeamManager({
  team,
  myId,
  locked,
  onChange,
  onLeft,
}: {
  team: Team;
  myId: number;
  locked: boolean;
  onChange: (t: Team) => void;
  onLeft: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(team.name);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inviteUrl = `${window.location.origin}/join/${team.invite_code}`;
  const isCaptain = team.captain_id === myId;
  const full = team.members.length >= team.max_team_size;

  async function run<T>(key: string, fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(key);
    setError(null);
    try {
      return await fn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.');
      return undefined;
    } finally {
      setBusy(null);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setError('Could not reach the clipboard - select the link and copy it by hand.');
    }
  }

  async function rename(e: FormEvent) {
    e.preventDefault();
    const updated = await run('rename', () => api.patch<Team>(`/api/teams/${team.id}`, { name }));
    if (updated) {
      onChange(updated);
      setRenaming(false);
    }
  }

  async function newLink() {
    if (!window.confirm('Make a new invite link? The current link will stop working straight away.')) return;
    const updated = await run('link', () => api.post<Team>(`/api/teams/${team.id}/invite-code`));
    if (updated) onChange(updated);
  }

  async function remove(memberId: number, memberName: string) {
    if (!window.confirm(`Remove ${memberName} from ${team.name}? They can rejoin only with a new invite link.`)) return;
    const updated = await run(`remove-${memberId}`, () => api.del<Team>(`/api/teams/${team.id}/members/${memberId}`));
    if (updated) onChange(updated);
  }

  async function makeCaptain(memberId: number, memberName: string) {
    if (!window.confirm(`Make ${memberName} the captain? You'll no longer be able to manage the team.`)) return;
    const updated = await run(`captain-${memberId}`, () =>
      api.post<Team>(`/api/teams/${team.id}/captain`, { user_id: memberId }),
    );
    if (updated) onChange(updated);
  }

  async function leave() {
    const last = team.members.length === 1;
    const message = last
      ? `You're the only member, so leaving deletes ${team.name} and any draft entry. Leave?`
      : `Leave ${team.name}?${isCaptain ? ' Captaincy passes to the longest-standing member.' : ''}`;
    if (!window.confirm(message)) return;
    setBusy('leave');
    setError(null);
    try {
      await api.post(`/api/teams/${team.id}/leave`);
      onLeft();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {renaming ? (
        <form className="flex flex-col gap-2 sm:flex-row sm:items-end" onSubmit={rename} noValidate>
          <Input
            label="Team name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            hint="3-40 characters."
            className="sm:w-72"
          />
          <div className="flex gap-2 sm:mb-6">
            <Button type="submit" variant="primary" size="sm" loading={busy === 'rename'} loadingLabel="Saving...">
              Save
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setRenaming(false);
                setName(team.name);
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-h3 text-ink-800">{team.name}</p>
          {isCaptain && !locked && (
            <Button variant="ghost" size="sm" onClick={() => setRenaming(true)}>
              Rename
            </Button>
          )}
        </div>
      )}

      <ul className="flex flex-col divide-y divide-border-subtle" aria-label="Team members">
        {team.members.map((m) => (
          <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-0">
            <span className="flex items-center gap-2 text-body text-ink-800">
              {m.name}
              {m.id === myId && <span className="text-meta text-ink-500">(you)</span>}
              {m.id === team.captain_id && <Badge status="info">Captain</Badge>}
            </span>
            {isCaptain && !locked && m.id !== myId && (
              <span className="flex gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  loading={busy === `captain-${m.id}`}
                  loadingLabel="Saving..."
                  onClick={() => makeCaptain(m.id, m.name)}
                >
                  Make captain
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  loading={busy === `remove-${m.id}`}
                  loadingLabel="Removing..."
                  onClick={() => remove(m.id, m.name)}
                >
                  Remove
                </Button>
              </span>
            )}
          </li>
        ))}
      </ul>
      <p className="text-meta text-ink-500">
        {team.members.length} / {team.max_team_size} members
      </p>

      {locked ? (
        <p className="text-meta text-ink-500">The deadline has passed, so the team can no longer change.</p>
      ) : full ? (
        <p className="text-meta text-ink-500">This team is full - the invite link can't be used until someone leaves.</p>
      ) : (
        <div className="flex flex-col gap-2 md:flex-row md:items-end">
          <Input label="Invite link" readOnly value={inviteUrl} className="flex-1" />
          <div className="flex gap-2">
            <Button variant="secondary" onClick={copy}>
              {copied ? 'Copied' : 'Copy'}
            </Button>
            {isCaptain && (
              <Button variant="ghost" loading={busy === 'link'} loadingLabel="Making..." onClick={newLink}>
                New link
              </Button>
            )}
          </div>
        </div>
      )}
      <span role="status" aria-live="polite" className="sr-only">
        {copied ? 'Link copied' : ''}
      </span>

      {error && (
        <p role="alert" className="text-meta text-danger-fg">
          {error}
        </p>
      )}

      {!locked && (
        <div>
          <Button variant="ghost" size="sm" loading={busy === 'leave'} loadingLabel="Leaving..." onClick={leave}>
            Leave team
          </Button>
        </div>
      )}
    </div>
  );
}
