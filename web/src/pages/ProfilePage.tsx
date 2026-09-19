import { useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { ImageUpload } from '../components/ImageUpload';
import { PasswordField } from '../components/auth/PasswordField';
import { Button, Card, RoleBadge } from '../components/ui';
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
              <dd className="text-body text-ink-800">{user.name}</dd>
            </div>
            <div>
              <dt className="text-label text-ink-500">Email</dt>
              <dd className="text-body text-ink-800">{user.email}</dd>
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
