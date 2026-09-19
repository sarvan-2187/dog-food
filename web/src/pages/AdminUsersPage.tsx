import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { RequireRole } from '../components/auth/guards';
import { EmptyState, ErrorState, SkeletonRows, Toast, ToastRegion } from '../components/feedback';
import { Badge, Button, Card, Input, RoleBadge } from '../components/ui';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import type { AdminUser, DuplicateMembership, JudgeInvite, Role, UserPage } from '../types';

const ROLES: Role[] = ['participant', 'judge', 'organizer'];

export function AdminUsersPage() {
  return (
    <RequireRole roles={['admin']}>
      <AdminUsers />
    </RequireRole>
  );
}

/**
 * PLAN.md 10.10. Before this, organizer accounts could only come from the
 * seed file. The admin role itself is never offered here - only the seed data
 * or the server's break-glass command make admins - and admin accounts can't be
 * changed or deactivated, so no admin session can lock the others out.
 */
function AdminUsers() {
  const { user: me } = useAuth();
  const [q, setQ] = useState('');
  const [role, setRole] = useState<Role | ''>('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<UserPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);

  const load = useCallback(() => {
    setError(null);
    const params = new URLSearchParams({ page: String(page) });
    if (q.trim()) params.set('q', q.trim());
    if (role) params.set('role', role);
    api
      .get<UserPage>(`/api/admin/users?${params}`)
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Could not load users.'));
  }, [q, role, page]);

  useEffect(load, [load]);

  async function change(u: AdminUser, patch: { role?: Role; is_active?: boolean }) {
    if (
      patch.is_active === false &&
      !window.confirm(`Deactivate ${u.name}? They're signed out everywhere and can't sign in until reactivated.`)
    ) {
      return;
    }
    if (patch.role && !window.confirm(`Make ${u.name} ${patch.role === 'organizer' ? 'an organizer' : `a ${patch.role}`}?`)) {
      return;
    }
    setBusy(u.id);
    try {
      const updated = await api.patch<AdminUser>(`/api/admin/users/${u.id}`, patch);
      setData((d) => (d ? { ...d, users: d.users.map((x) => (x.id === u.id ? updated : x)) } : d));
      setToast({ message: `${updated.name} updated.`, ok: true });
    } catch (err) {
      setToast({ message: err instanceof ApiError ? err.message : 'Could not update that account.', ok: false });
    } finally {
      setBusy(null);
    }
  }

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="mx-auto flex max-w-[1200px] flex-col gap-6 px-4 py-section md:px-6">
      <h1 className="text-h1 text-ink-900">Users</h1>

      <IntegrityWarning />

      <Card title="Accounts" meta={data ? `${data.total} total` : undefined}>
        <div data-tour="admin-users" className="flex flex-col gap-4">
          <form
            className="flex flex-col gap-3 sm:flex-row sm:items-end"
            onSubmit={(e) => {
              e.preventDefault();
              setPage(1);
              load();
            }}
          >
            <Input label="Search by name or email" value={q} onChange={(e) => setQ(e.target.value)} className="sm:w-80" />
            <label className="flex flex-col gap-1.5">
              <span className="text-label text-ink-800">Role</span>
              <select
                value={role}
                onChange={(e) => {
                  setRole(e.target.value as Role | '');
                  setPage(1);
                }}
                className="h-10 rounded-md border border-border bg-surface-0 px-3 text-body text-ink-800 focus:border-brand-500 focus:outline-none focus:ring-[3px] focus:ring-brand-500/20"
              >
                <option value="">Everyone</option>
                {(['participant', 'judge', 'organizer', 'admin'] as Role[]).map((r) => (
                  <option key={r} value={r}>
                    {r[0].toUpperCase() + r.slice(1)}s
                  </option>
                ))}
              </select>
            </label>
          </form>

          {error && <ErrorState description={error} onRetry={load} />}
          {!data && !error && <SkeletonRows rows={6} cols={3} />}
          {data && data.users.length === 0 && (
            <EmptyState title="No matching accounts" description="Try a different search." />
          )}
          {data && data.users.length > 0 && (
            <ul className="flex flex-col divide-y divide-border-subtle">
              {data.users.map((u) => {
                const locked = u.role === 'admin' || u.id === me?.id;
                return (
                  <li key={u.id} className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                    <span className="min-w-0">
                      <span className="flex items-center gap-2 text-body text-ink-800">
                        {u.name}
                        {!u.is_active && <Badge status="danger">Deactivated</Badge>}
                      </span>
                      <span className="block truncate text-meta text-ink-500">{u.email}</span>
                    </span>
                    {locked ? (
                      <RoleBadge role={u.role} />
                    ) : (
                      <span className="flex flex-wrap items-center gap-2">
                        <label>
                          <span className="sr-only">Role for {u.name}</span>
                          <select
                            value={u.role}
                            disabled={busy === u.id}
                            onChange={(e) => change(u, { role: e.target.value as Role })}
                            className="h-9 rounded-md border border-border bg-surface-0 px-2 text-meta text-ink-800 focus:border-brand-500 focus:outline-none focus:ring-[3px] focus:ring-brand-500/20"
                          >
                            {ROLES.map((r) => (
                              <option key={r} value={r}>
                                {r[0].toUpperCase() + r.slice(1)}
                              </option>
                            ))}
                          </select>
                        </label>
                        <Button
                          variant={u.is_active ? 'ghost' : 'secondary'}
                          size="sm"
                          loading={busy === u.id}
                          loadingLabel="Saving..."
                          onClick={() => change(u, { is_active: !u.is_active })}
                        >
                          {u.is_active ? 'Deactivate' : 'Reactivate'}
                        </Button>
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}

          {data && pages > 1 && (
            <div className="flex items-center justify-between gap-3">
              <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Previous
              </Button>
              <span className="text-meta text-ink-500">
                Page {page} of {pages}
              </span>
              <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
                Next
              </Button>
            </div>
          )}
        </div>
      </Card>

      <OrganizerInvites onToast={(message, ok) => setToast({ message, ok })} />

      <ToastRegion>
        {toast && (
          <Toast status={toast.ok ? 'success' : 'danger'} message={toast.message} onDismiss={() => setToast(null)} />
        )}
      </ToastRegion>
    </div>
  );
}

/** PLAN.md 10.2: memberships written before one-team-per-event was enforced. */
function IntegrityWarning() {
  const [rows, setRows] = useState<DuplicateMembership[] | null>(null);

  useEffect(() => {
    api
      .get<DuplicateMembership[]>('/api/admin/integrity')
      .then(setRows)
      .catch(() => setRows([]));
  }, []);

  if (!rows || rows.length === 0) return null;
  return (
    <div role="alert" className="rounded-md border border-border bg-warning-bg px-4 py-3 text-body text-warning-fg">
      <p className="mb-1 font-medium">
        {rows.length} {rows.length === 1 ? 'person is' : 'people are'} on more than one team in the same event:
      </p>
      <ul className="list-inside list-disc">
        {rows.map((r) => (
          <li key={`${r.event_id}-${r.user_id}`}>
            {r.user_name} - {r.teams} teams in {r.event_name}
          </li>
        ))}
      </ul>
      <p className="mt-1 text-meta">
        This data predates the one-team rule. Have them leave all but one team (a captain can also remove them).
      </p>
    </div>
  );
}

/**
 * The one route into the organizer role besides the seed data: a single-use,
 * expiring link, issued by an admin, exactly like judge invitations.
 */
function OrganizerInvites({ onToast }: { onToast: (message: string, ok: boolean) => void }) {
  const [invites, setInvites] = useState<JudgeInvite[] | null>(null);
  const [email, setEmail] = useState('');
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState<number | null>(null);

  const load = useCallback(() => {
    api
      .get<JudgeInvite[]>('/api/judge-invites?grants_role=organizer')
      .then(setInvites)
      .catch(() => setInvites([]));
  }, []);

  useEffect(load, [load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      await api.post<JudgeInvite>('/api/judge-invites', {
        grants_role: 'organizer',
        invited_email: email.trim() || null,
        expires_in_days: 14,
      });
      setEmail('');
      onToast('Organizer invitation created. Copy the link and send it.', true);
      load();
    } catch (err) {
      onToast(err instanceof ApiError ? err.message : 'Could not create the invitation.', false);
    } finally {
      setCreating(false);
    }
  }

  async function copy(invite: JudgeInvite) {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/judge-invite/${invite.token}`);
      setCopied(invite.id);
      window.setTimeout(() => setCopied(null), 2000);
    } catch {
      onToast('Could not reach the clipboard.', false);
    }
  }

  return (
    <Card title="Invite an organizer" meta="Admins only">
      <div className="flex flex-col gap-4">
        <form className="flex flex-col gap-3 sm:flex-row sm:items-start" onSubmit={create} noValidate>
          <Input
            label="Their email (optional)"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="sm:w-80"
            hint="For your own records - they can accept with any account."
          />
          <Button type="submit" variant="primary" className="sm:mt-7" loading={creating} loadingLabel="Creating...">
            Create invitation
          </Button>
        </form>
        {invites === null && <SkeletonRows rows={2} cols={2} />}
        {invites && invites.length > 0 && (
          <ul className="flex flex-col divide-y divide-border-subtle">
            {invites.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 py-2 first:pt-0">
                <span className="text-body text-ink-800">{i.invited_email || 'Unnamed invitation'}</span>
                <span className="flex items-center gap-2">
                  <Badge status={i.status === 'redeemed' ? 'success' : i.status === 'open' ? 'warning' : 'neutral'}>
                    {i.status === 'redeemed'
                      ? `Accepted by ${i.redeemed_by_name ?? 'someone'}`
                      : i.status === 'open'
                        ? 'Open'
                        : 'Expired'}
                  </Badge>
                  {i.status === 'open' && (
                    <Button variant="secondary" size="sm" onClick={() => copy(i)}>
                      {copied === i.id ? 'Copied' : 'Copy link'}
                    </Button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
        <span role="status" aria-live="polite" className="sr-only">
          {copied !== null ? 'Link copied' : ''}
        </span>
      </div>
    </Card>
  );
}
