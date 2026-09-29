import { useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ImageUpload } from '../components/ImageUpload';
import { PasswordField } from '../components/auth/PasswordField';
import { Badge, Button, Card, Input, RoleBadge } from '../components/ui';
import { ApiError, api } from '../lib/api';
import { useAuth } from '../lib/auth-context';
import { runTour } from '../lib/tour';

/**
 * Post-login account controls live here, not in the header - the header
 * stays identical to raptors.dev's real one (wordmark + hamburger only)
 * regardless of auth state, per an explicit request. Reached via "Profile"
 * in the hamburger menu, only shown once a user is signed in.
 */
export function ProfilePage() {
  const { user, logout, refresh } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);

  if (!user) return null; // RequireAuth already redirects; guards against a render race.

  async function onLogout() {
    setLoading(true);
    try {
      await logout();
      navigate('/');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-section">
      <Card title="Your profile">
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <RoleBadge role={user.role} />
          </div>
          <ImageUpload
            uploadUrl="/api/users/me/avatar"
            currentUrl={user.avatar_url}
            label="avatar"
            shape="circle"
            responseKey="avatar_url"
            onUploaded={() => refresh()}
          />
          <dl className="flex flex-col gap-3">
            <div>
              <dt className="text-label text-ink-500">Name</dt>
              <dd>
                <NameEditor name={user.name} onSaved={() => refresh()} />
              </dd>
            </div>
            <div>
              <dt className="text-label text-ink-500">Email</dt>
              <dd className="flex flex-col gap-2">
                <span className="text-body text-ink-800">{user.email}</span>
                <EmailVerification verified={Boolean(user.email_verified)} />
              </dd>
            </div>
          </dl>
          <div className="flex flex-wrap gap-3">
            <Button variant="secondary" onClick={() => runTour(user.role)}>
              Replay the guided tour
            </Button>
            <Button
              variant="secondary"
              loading={loading}
              loadingLabel="Signing out..."
              onClick={onLogout}
            >
              Log out
            </Button>
          </div>
        </div>
      </Card>

      <div className="mt-6">
        <ChangePasswordCard />
      </div>
    </div>
  );
}

/**
 * Some events only count votes from accounts whose owner has proven the
 * address (THREAT-MODEL entry 25). The link arrives by email and lands back
 * here with ?verified=1 (or 0 if it was stale or tampered with).
 */
function EmailVerification({ verified }: { verified: boolean }) {
  const [params] = useSearchParams();
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<string | null>(
    params.get('verified') === '0' ? 'That link has expired or is not valid. Send a new one.' : null,
  );

  if (verified) return <Badge status="success"><span aria-hidden="true">&#10003;</span> Verified</Badge>;

  async function send() {
    setSending(true);
    try {
      const r = await api.post<{ sent_to: string }>('/api/auth/verify-email');
      setMessage(`Check ${r.sent_to} for a link. It works for 24 hours.`);
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : 'Could not send a verification link.');
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <Button variant="secondary" size="sm" loading={sending} loadingLabel="Sending..." onClick={send}>
        Send verification link
      </Button>
      {message && <p role="status" className="text-meta text-ink-600">{message}</p>}
    </div>
  );
}

/**
 * PLAN.md Phase 9.5. Changing the password bumps the account's session
 * version on the server, which signs out every other device; this one gets a
 * fresh cookie in the same response, so nothing here needs to re-login.
 */
function ChangePasswordCard() {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [touched, setTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [currentError, setCurrentError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const nextError = touched && next.length < 8 ? 'Use at least 8 characters.' : undefined;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    setSaved(false);
    setCurrentError(null);
    setError(null);
    if (!current || next.length < 8) {
      if (!current) setCurrentError('Enter your current password.');
      return;
    }
    setSaving(true);
    try {
      await api.post('/api/auth/password', { current_password: current, new_password: next });
      setCurrent('');
      setNext('');
      setTouched(false);
      setSaved(true);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Could not change your password. Please try again.';
      // A wrong current password belongs next to that field, not in a toast.
      if (err instanceof ApiError && err.status === 400) setCurrentError(message);
      else setError(message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="Change password">
      <form className="flex flex-col gap-4" onSubmit={onSubmit} noValidate>
        <p className="text-body text-ink-600">This signs you out on every other device.</p>
        <PasswordField
          label="Current password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          error={currentError ?? undefined}
        />
        <PasswordField
          label="New password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          onBlur={() => next && setTouched(true)}
          error={nextError}
          hint="At least 8 characters."
        />
        {error && (
          <p role="alert" className="text-meta text-danger-fg">
            {error}
          </p>
        )}
        {saved && (
          <p role="status" className="text-meta text-success-fg">
            Password changed. Every other device has been signed out.
          </p>
        )}
        <div>
          <Button type="submit" variant="primary" loading={saving} loadingLabel="Saving...">
            Change password
          </Button>
        </div>
      </form>
    </Card>
  );
}

/** PLAN.md 10.13. Same 2-60 character rule as sign-up, checked inline. */
function NameEditor({ name, onSaved }: { name: string; onSaved: () => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(name);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmed = value.trim();
  const inlineError = trimmed.length < 2 || trimmed.length > 60 ? 'Use 2-60 characters.' : undefined;

  async function save(e: FormEvent) {
    e.preventDefault();
    if (inlineError) return;
    setSaving(true);
    setError(null);
    try {
      await api.patch('/api/auth/me', { name: trimmed });
      onSaved();
      setEditing(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save your name.');
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    return (
      <span className="flex flex-wrap items-center gap-3">
        <span className="text-body text-ink-800">{name}</span>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setValue(name);
            setEditing(true);
          }}
        >
          Edit
        </Button>
      </span>
    );
  }
  return (
    <form className="flex flex-col gap-2 sm:flex-row sm:items-start" onSubmit={save} noValidate>
      <Input
        label="Display name"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        error={error ?? inlineError}
        className="sm:w-72"
      />
      <div className="flex gap-2 sm:mt-7">
        <Button type="submit" variant="primary" size="sm" loading={saving} loadingLabel="Saving...">
          Save
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
